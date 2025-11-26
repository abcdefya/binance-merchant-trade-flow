import os
import yaml
from pathlib import Path
from typing import Optional, List
from google.cloud import storage


def _upload_tree_worker(job_args):
    """
    Upload helper for ProcessPoolExecutor. Re-creates a storage client per job
    to avoid pickling shared clients/buckets across processes.
    """
    bucket_name, blob_name, local_file = job_args
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_file)
    return blob_name


class GCSManager:
    """
    Robust, production-grade Google Cloud Storage Manager.
    Designed for real-world AI/ML workflows, data pipelines and cloud systems.
    """

    def __init__(self, config_path: str = "configs.yaml"):
        self.config = self._load_config(config_path)

        credential_path = self.config["gcs"].get("credential_path")
        if credential_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path

        self.client = storage.Client()
        self.default_bucket = self.config["gcs"]["default_bucket"]
        self.default_location = self.config["gcs"]["default_location"]

    def _load_config(self, path: str) -> dict:
        cfg_path = Path(path)
        if not cfg_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)


    def create_bucket(
        self,
        bucket_name: Optional[str] = None,
        location: Optional[str] = None
    ):
        bucket_name = bucket_name or self.default_bucket
        location = location or self.default_location

        bucket = self.client.bucket(bucket_name)
        bucket = self.client.create_bucket(bucket, location=location)

        print(f"[GCS] Bucket created → gs://{bucket_name} (location={location})")
        return bucket


    def upload_file(
        self,
        local_file: str,
        remote_path: Optional[str] = None,
        bucket_name: Optional[str] = None
    ):
        bucket_name = bucket_name or self.default_bucket
        bucket = self.client.bucket(bucket_name)

        local_path = Path(local_file)
        if not local_path.exists():
            raise FileNotFoundError(f"File not found: {local_file}")

        remote_path = remote_path or local_path.name
        remote_path = remote_path.replace("\\", "/")

        blob = bucket.blob(remote_path)
        blob.upload_from_filename(str(local_path))

        print(f"[GCS] Uploaded → {local_file} → gs://{bucket_name}/{remote_path}")
        return f"gs://{bucket_name}/{remote_path}"


    def upload_folder(
        self,
        source_folder: Optional[str] = None,
        destination_prefix: Optional[str] = None,
        bucket_name: Optional[str] = None
    ):
        bucket_name = bucket_name or self.default_bucket
        bucket = self.client.bucket(bucket_name)

        source_folder = source_folder or self.config["upload"]["source_folder"]
        destination_prefix = destination_prefix or self.config["upload"]["destination_prefix"]

        src = Path(source_folder)
        if not src.exists():
            raise FileNotFoundError(f"Folder not found: {source_folder}")

        print(f"[GCS] Uploading folder recursively → {src}")

        for file_path in src.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(src)
                remote_path = f"{destination_prefix}/{rel}".replace("\\", "/")

                blob = bucket.blob(remote_path)
                blob.upload_from_filename(str(file_path))

                print(f"  ✔ {file_path} → gs://{bucket_name}/{remote_path}")

        print("[GCS] Folder upload completed.")

    def upload_multi_files(
        self,
        filenames: List[str],
        source_directory: str = "",
        bucket_name: Optional[str] = None,
        workers: int = 16,
        use_threads: bool = False
    ):
        from google.cloud.storage import transfer_manager

        bucket_name = bucket_name or self.default_bucket
        bucket = self.client.bucket(bucket_name)

        worker_type = (
            transfer_manager.THREAD if use_threads else transfer_manager.PROCESS
        )

        print(
            f"[GCS] Parallel upload: {len(filenames)} files "
            f"(workers={workers}, mode={'thread' if use_threads else 'process'})"
        )

        results = transfer_manager.upload_many_from_filenames(
            bucket=bucket,
            filenames=filenames,
            source_directory=source_directory,
            max_workers=workers,
            worker_type=worker_type,
        )

        print("\n[GCS] Upload results:")
        for name, result in zip(filenames, results):
            if isinstance(result, Exception):
                print(f"  ❌ {name} → {result}")
            else:
                print(f"  ✔ {name}")

        print("\n[GCS] Multi-file upload completed.\n")

    def upload_tree_parallel(
        self,
        root_folder: str,
        destination_prefix: str = "",
        bucket_name: Optional[str] = None,
        workers: int = 16,
        use_threads: bool = False
    ):
        """
        Upload entire nested directory tree in parallel.
        Compatible with all google-cloud-storage versions (no UploadJob required).
        """

        bucket_name = bucket_name or self.default_bucket
        bucket = self.client.bucket(bucket_name)

        root = Path(root_folder)
        if not root.exists():
            raise FileNotFoundError(f"Folder not found: {root_folder}")

        # 1️⃣ Scan all files
        file_paths = []
        blob_paths = []

        for fp in root.rglob("*"):
            if fp.is_file():
                file_paths.append(str(fp))
                rel = fp.relative_to(root)
                blob_paths.append(
                    f"{destination_prefix}/{rel}".replace("\\", "/")
                    if destination_prefix else str(rel).replace("\\", "/")
                )

        print(f"[GCS] Files found: {len(file_paths)}")
        print(f"[GCS] Starting parallel upload with {workers} workers…")

        # pair each local file with its blob name
        if not file_paths:
            print("[GCS] No files discovered to upload.")
            return

        jobs = list(zip(file_paths, blob_paths))

        # 3️⃣ Run parallel workers
        from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

        if use_threads:
            print("[GCS] Using ThreadPoolExecutor for uploads.")

            def _upload_one(job):
                local_file, blob_name = job
                blob = bucket.blob(blob_name)
                blob.upload_from_filename(local_file)
                return blob_name

            Executor = ThreadPoolExecutor
            worker_fn = _upload_one
            job_iter = jobs
        else:
            print("[GCS] Using ProcessPoolExecutor for uploads.")
            Executor = ProcessPoolExecutor
            worker_fn = _upload_tree_worker
            job_iter = [
                (bucket_name, blob_name, local_file)
                for local_file, blob_name in jobs
            ]

        with Executor(max_workers=workers) as executor:
            results = list(executor.map(worker_fn, job_iter))

        # 4️⃣ Done
        for blob_name in results:
            print(f"  ✔ gs://{bucket_name}/{blob_name}")

        print("\n[GCS] Parallel tree upload completed.\n")
