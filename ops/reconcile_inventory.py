#!/usr/bin/env ../venv/bin/python3
"""
reconcile_inventory.py — soft-delete DynamoDB records not present in any current tfstate.

Usage:
  python3 ops/reconcile_inventory.py --dry-run                     # show what would be deleted
  python3 ops/reconcile_inventory.py                               # actually soft-delete
  python3 ops/reconcile_inventory.py --profile myprofile
  python3 ops/reconcile_inventory.py --delete-id i-0079a6ebb2d95a73e   # delete one resource by ID
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Attr

WORKSPACES_FILE = Path(__file__).parent.parent / "config" / "terraform_workspaces.json"
SOFT_DELETE_TTL = 604_800  # 7 days


def load_live_resources(workspaces: list[dict], profile: str | None) -> set[tuple[str, str]]:
    """Return {(resource_type, resource_id)} for every resource in every tfstate."""
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    s3      = session.client("s3")
    live: set[tuple[str, str]] = set()

    for ws in workspaces:
        bucket = ws.get("tfstate_bucket")
        key    = ws.get("tfstate_key")
        if not bucket or not key:
            continue
        try:
            body  = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            state = json.loads(body)
        except Exception as exc:
            print(f"  WARN: cannot read s3://{bucket}/{key}: {exc}")
            continue

        for res in state.get("resources", []):
            if res.get("mode") != "managed":
                continue
            for inst in res.get("instances", []):
                res_id = inst.get("attributes", {}).get("id", "")
                if res_id:
                    live.add((res.get("type", ""), res_id))

        print(f"  {ws['id']}: {sum(1 for r in state.get('resources', []) if r.get('mode') == 'managed')} resources")

    return live


def reconcile(table_name: str, region: str, live: set[tuple[str, str]],
              dry_run: bool, profile: str | None) -> None:
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    table   = session.resource("dynamodb", region_name=region).Table(table_name)

    scan_kwargs: dict = {
        "FilterExpression": Attr("deleted").eq(False) | Attr("deleted").not_exists(),
        "ProjectionExpression": "PK, SK, resource_type, resource_id, account_id, #rgn",
        "ExpressionAttributeNames": {"#rgn": "region"},
    }

    stale = []
    while True:
        resp = table.scan(**scan_kwargs)
        for item in resp.get("Items", []):
            key = (item.get("resource_type", ""), item.get("resource_id", ""))
            if key not in live:
                stale.append(item)
        if not resp.get("LastEvaluatedKey"):
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    print(f"\n{'[DRY RUN] Would soft-delete' if dry_run else 'Soft-deleting'} {len(stale)} stale record(s):\n")
    ttl = int(time.time()) + SOFT_DELETE_TTL
    now = datetime.now(timezone.utc).isoformat()

    for item in stale:
        print(f"  {item['resource_type']}  {item['resource_id']}  ({item.get('region', '?')} / {item.get('account_id', '?')})")
        if not dry_run:
            table.update_item(
                Key={"PK": item["PK"], "SK": item["SK"]},
                UpdateExpression="SET deleted = :t, deleted_at = :da, ttl_timestamp = :ttl",
                ExpressionAttributeValues={":t": True, ":da": now, ":ttl": ttl},
            )


def delete_by_id(table_name: str, region: str, resource_id: str,
                 dry_run: bool, profile: str | None) -> None:
    """Scan for a record by resource_id and soft-delete it."""
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    table   = session.resource("dynamodb", region_name=region).Table(table_name)

    resp = table.scan(
        FilterExpression=Attr("resource_id").eq(resource_id),
        ProjectionExpression="PK, SK, resource_type, account_id, #rgn",
        ExpressionAttributeNames={"#rgn": "region"},
    )
    items = resp.get("Items", [])

    if not items:
        print(f"No record found for resource_id={resource_id!r}")
        return

    ttl = int(time.time()) + SOFT_DELETE_TTL
    now = datetime.now(timezone.utc).isoformat()

    for item in items:
        print(f"{'[DRY RUN] Would soft-delete' if dry_run else 'Soft-deleting'}: "
              f"{item['resource_type']}  {resource_id}  "
              f"({item.get('region', '?')} / {item.get('account_id', '?')})")
        if not dry_run:
            table.update_item(
                Key={"PK": item["PK"], "SK": item["SK"]},
                UpdateExpression="SET deleted = :t, deleted_at = :da, ttl_timestamp = :ttl",
                ExpressionAttributeValues={":t": True, ":da": now, ":ttl": ttl},
            )


def main():
    parser = argparse.ArgumentParser(description="Reconcile DynamoDB inventory against current tfstate files")
    parser.add_argument("--table",     default="askloud-central-ops-inventory", help="DynamoDB table name")
    parser.add_argument("--region",    default="ap-south-1",                    help="AWS region of the DynamoDB table")
    parser.add_argument("--profile",   default=None,                            help="AWS CLI profile name")
    parser.add_argument("--dry-run",   action="store_true",                     help="Print what would be deleted without making changes")
    parser.add_argument("--delete-id", default=None, metavar="RESOURCE_ID",     help="Soft-delete a single resource by its ID")
    args = parser.parse_args()

    if args.delete_id:
        delete_by_id(args.table, args.region, args.delete_id, args.dry_run, args.profile)
        return

    workspaces = json.loads(WORKSPACES_FILE.read_text())["workspaces"]
    print("Reading tfstate files:")
    live = load_live_resources(workspaces, args.profile)
    print(f"\nTotal live resources across all workspaces: {len(live)}")

    reconcile(args.table, args.region, live, args.dry_run, args.profile)


if __name__ == "__main__":
    main()
