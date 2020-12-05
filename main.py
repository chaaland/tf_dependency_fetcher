"""Script to download tensorflow dependencies for building it offline."""
import argparse
import hashlib
from pathlib import Path
from tqdm import tqdm

import re
import requests


class TensorflowRepo:
    DEPENDENCY_URL_PATTERN = '"(https://.*)",?'
    SEMVER_PATTERN = "[\d.]+"

    def __init__(self, tf_dir):
        self._tf_dir = tf_dir
        self._tf_version = self.get_tf_version()

    def get_tf_version(self):
        setup_py_file = self._tf_dir.glob("setup.py")
        with open(setup_py_file, "rt") as f:
            contents = f.read()
        tf_version = re.findall(rf"_VERSION = ({SEMVER_PATTERN})").group(1)
        return tf_version

    def download_build_dependencies(self, download_dir):
        urls = self._get_dependency_urls()
        print(f"Found {len(urls)} dependency urls.")
        self._download_urls(download_dir, urls)
    
    def _download_urls(self, download_dir, urls_to_download):
        failed_downloads = []
        num_skipped = 0
        num_success = 0
        
        for url in tqdm(urls_to_download):
            if self._is_cached(download_dir, url):
                num_skipped += 1
                continue
            try:
                response = requests.get(url)
                if response.ok:
                    self._cache_dependency(download_dir, response)
                    num_success += 1
                else:
                    raise Exception(f"Status code {response.status_code} for {url}.")
            except Exception as e:
                print(e)
                failed_downloads.append(url)
                print(f"FAILURE: {url}", flush=True)
            
        print(f"Completed downloads for tensorflow=={self._tf_version}.")
        if failed_downloads:
            print("Failed downloads")
            print("\n\t".join(failed_downloads), flush=True)

        print(f"{len(failed_downloads)} dependency downloads failed.", flush=True)
        print(f"{num_skipped} dependency downloads skipped.", flush=True)
        print(f"{num_success} dependency downloads completed.", flush=True)

    def _get_dependency_urls(self):
        files_with_deps = self._get_files_listing_deps()
        print(f"Found {len(files_with_deps)} files containing dependencies.", flush=True)
        urls = []
        for file in files_with_deps:
            urls += self._get_deps_from_file(file)
        return urls

    def _is_cached(self, download_dir, url):
        cached_name = self._ckpt_filename(url)
        all_cached_files = [p.name for p in download_dir.glob("@*.txt")]
        return cached_name in all_cached_files

    def _cache_dependency(self, download_dir, response):
        cache_file = download_dir / self._get_response_filename(response)
        with open(cache_file, "wb") as f:
            f.write(response.content)
        
        requested_url = response.history[0].url if response.history else response.url
        dep_ckpt_filename = self._ckpt_filename(requested_url)
        dep_ckpt_file = download_dir / dep_ckpt_filename
        dep_ckpt_file.touch()

    def _ckpt_filename(self, url):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        filename = f"@{url_hash}.txt"
        return filename

    def _get_response_filename(self, response):
        try:
            key = "Content-Disposition"
            if key in response.headers:
                content = response.headers[key]
            elif key.lower() in response.headers:
                content = response.headers[key.lower()]
            else:
                raise KeyError(f"No field '{key}'")
            fname = re.findall('filename=(.+)', content)[0]
            fname.strip().strip(",").strip("\"")
        except:
            fname = Path(response.url).name

        return fname

    def _get_files_listing_deps(self):
        tf_dir = Path(self._tf_dir)
        files_listing_deps = list(tf_dir.glob("**/workspace.bzl"))
        return files_listing_deps
   
    def _get_deps_from_file(self, file):
        with open(file, "rt") as f:
            contents = f.read()
            dependency_urls = self._extract_dependency_urls(contents)

        return dependency_urls
    
    def _extract_dependency_urls(self, contents, remove_mirrors=True):
        urls = re.findall(self.DEPENDENCY_URL_PATTERN, contents)
        if remove_mirrors:
            urls = [link for link in urls if not self._is_mirror_url(link)]

        return urls

    def _is_mirror_url(self, url):
        return "mirror.bazel.build" in url or "mirror.tensorflow.org" in url


def main(args):
    tf_dir = Path(args.tensorflow_repo)
    download_dir = Path(args.download_dir)
    download_dir.mkdir(exist_ok=True, parents=True)

    tf_repo = TensorflowRepo(tf_dir)
    tf_repo.download_build_dependencies(download_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        "Program for making a best effort to download all"
        " the TensorFlow dependencies needed to build the"
        " package from source."
    )
    parser.add_argument("--tensorflow-repo", type=str)
    parser.add_argument("--download-dir", type=str)
    args = parser.parse_args()

    main(args)
