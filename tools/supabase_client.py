"""Thin Supabase wrappers for episode/short state and storage."""
from __future__ import annotations
import os
from typing import Any
from supabase import create_client, Client


def get_client() -> Client:
    """Return a Supabase client built from SUPABASE_URL and SUPABASE_KEY env vars."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def insert_episode(client: Client, data: dict[str, Any]) -> dict[str, Any]:
    res = client.table("episodes").insert(data).execute()
    return res.data[0]


def get_episodes_by_status(client: Client, status: str) -> list[dict[str, Any]]:
    res = client.table("episodes").select("*").eq("status", status).execute()
    return res.data


def update_episode_status(client: Client, episode_id: int, status: str, **fields: Any) -> dict[str, Any]:
    fields["status"] = status
    res = client.table("episodes").update(fields).eq("id", episode_id).execute()
    return res.data[0] if res.data else {}


def insert_short(client: Client, data: dict[str, Any]) -> dict[str, Any]:
    res = client.table("shorts").insert(data).execute()
    return res.data[0]


def get_shorts_by_status(client: Client, status: str) -> list[dict[str, Any]]:
    res = client.table("shorts").select("*").eq("status", status).execute()
    return res.data


def update_short_status(client: Client, short_id: int, status: str, **fields: Any) -> dict[str, Any]:
    fields["status"] = status
    res = client.table("shorts").update(fields).eq("id", short_id).execute()
    return res.data[0] if res.data else {}


def upload_file(client: Client, bucket: str, dest_path: str, src_file_path: str) -> str:
    """Upload local file to a Supabase Storage bucket. Returns the dest_path."""
    with open(src_file_path, "rb") as f:
        client.storage.from_(bucket).upload(dest_path, f)
    return dest_path


def signed_url(client: Client, bucket: str, path: str, ttl_seconds: int = 3600) -> str:
    res = client.storage.from_(bucket).create_signed_url(path, ttl_seconds)
    return res["signedURL"]
