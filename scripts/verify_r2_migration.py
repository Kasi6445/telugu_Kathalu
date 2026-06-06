"""
Verify that all story media files (images + audio) exist in Cloudflare R2.

Reads stories/index.json for story list, then for each story reads its
story.json to get the scene count, and checks R2 for every expected file.

Usage:
    python scripts/verify_r2_migration.py

Required env vars:
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_ACCOUNT_ID
    R2_BUCKET_NAME
"""

import json
import os
import sys

import boto3
from botocore.exceptions import ClientError


def get_r2_client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def key_exists(client, bucket, key):
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def load_stories(index_path="stories/index.json"):
    with open(index_path, encoding="utf-8") as f:
        return json.load(f)["stories"]


def get_scene_count(story_id):
    path = os.path.join("stories", story_id, "story.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return len(data.get("scenes", data.get("slides", [])))
    except FileNotFoundError:
        return None


def main():
    bucket = os.environ["R2_BUCKET_NAME"]
    client = get_r2_client()

    stories = load_stories()
    total = len(stories)
    fully_migrated = 0
    missing_files = []

    print(f"Checking {total} stories against R2 bucket '{bucket}' ...\n")

    for story in stories:
        story_id = story["id"]
        slug = story["slug"]
        scene_count = get_scene_count(story_id)

        if scene_count is None:
            print(f"  WARN  [{slug}] story.json not found locally — skipping")
            continue

        story_missing = []
        for i in range(1, scene_count + 1):
            image_key = f"stories/{story_id}/images/scene{i}.jpg"
            audio_key = f"stories/{story_id}/audio/scene{i}.mp3"

            if not key_exists(client, bucket, image_key):
                story_missing.append(image_key)
            if not key_exists(client, bucket, audio_key):
                story_missing.append(audio_key)

        if story_missing:
            missing_files.extend(story_missing)
            print(f"  MISS  [{slug}]  {len(story_missing)} file(s) missing")
            for f in story_missing:
                print(f"          {f}")
        else:
            fully_migrated += 1
            print(f"  OK    [{slug}]  {scene_count * 2} files verified")

    print("\n" + "=" * 60)
    print(f"Total stories    : {total}")
    print(f"Fully migrated   : {fully_migrated}")
    print(f"Missing files    : {len(missing_files)}")

    if missing_files:
        print("\nMissing file list:")
        for f in missing_files:
            print(f"  {f}")
        sys.exit(1)
    else:
        print("\nAll media files confirmed in R2.")
        sys.exit(0)


if __name__ == "__main__":
    main()
