import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
import asyncio

from synthetic_data_generator.s3_client import S3Client
from synthetic_data_generator.local_file_client import LocalFileClient
from synthetic_data_generator import utils


class CLIArgs(argparse.Namespace):
    bundle: str
    output: str | None = None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Get unique resource types from a FHIR bundle."
    )
    parser.add_argument(
        "--bundle",
        required=True,
        help="Path to the FHIR bundle.",
    )
    parser.add_argument(
        "--output",
        help="Path to the output file.",
    )
    return parser.parse_args(namespace=CLIArgs())


def extract_resource_types(bundle_json: dict[str, Any]) -> set[str]:
    resource_types = set()
    for entry in bundle_json.get("entry", []):
        resource = entry.get("resource", {})
        if "resourceType" in resource:
            resource_types.add(resource["resourceType"])
    return resource_types

async def process_s3_file(bundle_info: dict[str, Any], temp_path: Path, s3_client: S3Client, all_resource_types: set[str]):
    bundle_filename = bundle_info["filename"]

    try:
        print(f"Processing bundle: {bundle_filename}")
        local_bundle_path = s3_client.download_file(
            bundle_info["bucket"], bundle_info["key"], temp_path
        )
        with open(local_bundle_path) as f:
            resource_types = extract_resource_types(json.load(f))
            all_resource_types.update(resource_types)

        local_bundle_path.unlink()
    except Exception as e:
        print(f"Error processing bundle {bundle_filename}: {e}")
        print("Skipping bundle and continuing...")


async def async_main():
    args = parse_args()

    try:
        # bundle_path = Path(args.bundle)
        # if not bundle_path.exists():
        #     print(f"Error: Bundle file not found: {bundle_path}")
        #     sys.exit(1)

        is_s3 = utils.is_s3_path(args.bundle)

        s3_client = S3Client()
        local_file_client = LocalFileClient()

        if is_s3:
            bucket, prefix = utils.parse_s3_path(args.bundle)
            bundles = s3_client.list_objects(
                bucket,
                prefix,
                pattern="*.json",
                exclude_objects=["organizations.json", "practitioners.json"],
                limit=None,
            )
        else:
            bundles = local_file_client.list_local_files(
                args.bundle,
                pattern="*.json",
                exclude_files=["organizations.json", "practitioners.json"],
                limit=None,
            )

        print(f"Bundles: {len(bundles)}")
        print("=" * 80)
        print([bundle.get("filename") if is_s3 else bundle.name for bundle in bundles])
        print("=" * 80)

        all_resource_types = set()
        if bundles:
            if is_s3:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)

                    await asyncio.gather(
                        *[process_s3_file(bundle_info, temp_path, s3_client, all_resource_types) for bundle_info in bundles]
                    )

                    # for bundle_info in bundles:
                    #     bundle_filename = bundle_info["filename"]
                    #
                    #     try:
                    #         print(f"Processing bundle: {bundle_filename}")
                    #         local_bundle_path = s3_client.download_file(
                    #             bundle_info["bucket"], bundle_info["key"], temp_path
                    #         )
                    #         with open(local_bundle_path) as f:
                    #             resource_types = extract_resource_types(json.load(f))
                    #             all_resource_types.update(resource_types)
                    #
                    #         local_bundle_path.unlink()
                    #     except Exception as e:
                    #         print(f"Error processing bundle {bundle_filename}: {e}")
                    #         print(f"Skipping bundle and continuing...")
                    #         continue

            else:
                for bundle_path in bundles:
                    with open(bundle_path) as f:
                        resource_types = extract_resource_types(json.load(f))
                        all_resource_types.update(resource_types)

        print(f"Unique resource types: {len(all_resource_types)}")
        print("=" * 80)
        print(all_resource_types)
        print("=" * 80)

        with open(args.output, "w") as f:
            json.dump(list(all_resource_types), f, indent=2)
        print(f"Saved to: {args.output}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
