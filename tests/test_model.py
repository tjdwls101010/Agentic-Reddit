from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema

from agentic_reddit.model import (
    build_comment,
    build_post,
    build_subreddit,
    build_user,
    comment_schema_fields,
    json_schema,
    media_schema_fields,
    post_schema_fields,
    schema_fields,
    subreddit_schema_fields,
    user_schema_fields,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_CAPTURED_AT = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)


def _fixture(name: str):
    return json.loads((_FIXTURES / name).read_text())


def test_post_normalization_uses_iso_utc_and_gallery_media() -> None:
    raw = _fixture("subreddit_hot.json")["data"]["children"][0]["data"]

    post = build_post(raw, captured_at=_CAPTURED_AT)

    assert post.to_dict()["created_at"] == "2024-01-01T00:00:00Z"
    assert post.to_dict()["captured_at"] == "2024-01-02T03:04:05Z"
    assert post.to_dict()["link_url"] == "https://example.invalid/article"
    assert [item["kind"] for item in post.to_dict()["media"]] == ["gallery", "gallery"]
    assert "raw" not in post.to_dict()
    assert build_post(raw, captured_at=_CAPTURED_AT, include_raw=True).to_dict()["raw"] == raw


def test_comment_normalization_is_recursive_and_counts_more_nodes() -> None:
    raw = _fixture("post_with_comment_tree.json")[1]["data"]["children"][0]["data"]

    comment = build_comment(raw, captured_at=_CAPTURED_AT)

    assert comment.to_dict()["permalink"].startswith("https://www.reddit.com/")
    assert comment.replies[0].id == "comment02"
    assert comment.more_count == 4


def test_subreddit_uses_over18_not_post_over_18_spelling() -> None:
    raw = _fixture("subreddit_about.json")["data"]

    subreddit = build_subreddit(raw, captured_at=_CAPTURED_AT)

    assert subreddit.over_18 is True
    assert subreddit.icon_url == "https://example.invalid/community.png"
    assert subreddit.to_dict()["url"] == "https://www.reddit.com/r/SyntheticSpace/"


def test_nsfw_state_preserves_only_upstream_booleans() -> None:
    cases = (
        ("true", True, True),
        ("false", False, False),
        ("missing", None, None),
        ("malformed", "yes", None),
    )
    for _, value, expected in cases:
        post_raw = {"id": "post001"}
        subreddit_raw = {"id": "subreddit001", "display_name": "SyntheticSpace"}
        if value is not None:
            post_raw["over_18"] = value
            subreddit_raw["over18"] = value

        assert build_post(post_raw, captured_at=_CAPTURED_AT).to_dict()["over_18"] is expected
        assert (
            build_subreddit(subreddit_raw, captured_at=_CAPTURED_AT).to_dict()["over_18"]
            is expected
        )


def test_user_normalization_and_optional_raw() -> None:
    raw = {
        "id": "user001",
        "name": "synthetic_dana",
        "created_utc": 1704067200,
        "link_karma": 11,
        "comment_karma": 12,
        "total_karma": 23,
        "verified": True,
        "icon_img": "https://example.invalid/avatar.png",
        "accept_followers": True,
    }

    user = build_user(raw, captured_at=_CAPTURED_AT)

    assert user.to_dict()["fullname"] == "t2_user001"
    assert user.to_dict()["verified"] is True
    assert "raw" not in user.to_dict()


def test_schema_fields_match_serialized_keys_and_have_descriptions() -> None:
    field_sets = [
        schema_fields(),
        post_schema_fields(),
        comment_schema_fields(),
        subreddit_schema_fields(),
        user_schema_fields(),
        media_schema_fields(),
    ]

    for fields in field_sets:
        assert fields
        assert all(field["description"] for field in fields)
        assert [field["name"] for field in fields] == list(
            dict.fromkeys(field["name"] for field in fields)
        )
    post_fields = {field["name"]: field for field in post_schema_fields()}
    comment_fields = {field["name"]: field for field in comment_schema_fields()}
    subreddit_fields = {field["name"]: field for field in subreddit_schema_fields()}
    assert post_fields["id"] == {
        "name": "id",
        "type": "string",
        "description": "Reddit base-36 identifier without its fullname prefix.",
        "always_present": True,
    }
    assert post_fields["over_18"]["type"] == "boolean | null"
    assert subreddit_fields["over_18"]["type"] == "boolean | null"
    assert post_fields["media"]["type"] == "array<Media>"
    assert comment_fields["replies"]["type"] == "array<Comment>"
    assert [field["name"] for field in schema_fields()] == [
        field["name"] for field in post_schema_fields()
    ]


def test_all_record_types_validate_against_generated_schema() -> None:
    post_raw = _fixture("subreddit_hot.json")["data"]["children"][0]["data"]
    comment_raw = _fixture("post_with_comment_tree.json")[1]["data"]["children"][0]["data"]
    subreddit_raw = _fixture("subreddit_about.json")["data"]
    user_raw = {
        "id": "user001",
        "name": "synthetic_dana",
        "created_utc": 1704067200,
    }
    validator = jsonschema.Draft202012Validator(json_schema())

    for record in (
        build_post(post_raw, captured_at=_CAPTURED_AT),
        build_comment(comment_raw, captured_at=_CAPTURED_AT),
        build_subreddit(subreddit_raw, captured_at=_CAPTURED_AT),
        build_user(user_raw, captured_at=_CAPTURED_AT),
    ):
        validator.validate(record.to_dict())
    schema = json_schema()
    assert schema["$defs"]["Post"]["properties"]["over_18"]["type"] == ["boolean", "null"]
    assert schema["$defs"]["Subreddit"]["properties"]["over_18"]["type"] == ["boolean", "null"]
    assert schema["$defs"]["Post"]["properties"]["media"]["items"] == {"$ref": "#/$defs/Media"}
    assert schema["$defs"]["Comment"]["properties"]["replies"]["items"] == {
        "$ref": "#/$defs/Comment"
    }


def test_media_normalization_uses_reddit_media_fields() -> None:
    gallery = build_post(_fixture("gallery_post.json"), captured_at=_CAPTURED_AT).to_dict()["media"]
    video = build_post(_fixture("video_post.json"), captured_at=_CAPTURED_AT).to_dict()["media"]
    image = build_post(_fixture("image_post.json"), captured_at=_CAPTURED_AT).to_dict()["media"]
    embed = build_post(
        {
            "id": "embed001",
            "url": "https://embed.example.invalid/watch/synthetic",
            "media": {"oembed": {"html": "<iframe>", "width": 640, "height": 360}},
        },
        captured_at=_CAPTURED_AT,
    ).to_dict()["media"]

    assert gallery == [
        {
            "kind": "gallery",
            "url": "https://example.invalid/gallery-one.png?x=1&y=2",
            "width": 640,
            "height": 480,
        },
        {
            "kind": "gallery",
            "url": "https://example.invalid/gallery-two.png",
            "width": 800,
            "height": 600,
        },
    ]
    assert video == [
        {
            "kind": "video",
            "url": "https://v.redd.it/synthetic/DASH_720.mp4?source=fallback",
            "width": 1280,
            "height": 720,
        }
    ]
    assert image == [
        {
            "kind": "image",
            "url": "https://i.example.invalid/synthetic-image.png",
            "width": 1024,
            "height": 768,
        }
    ]
    assert embed == [
        {
            "kind": "embed",
            "url": "https://embed.example.invalid/watch/synthetic",
            "width": 640,
            "height": 360,
        }
    ]
    assert build_post({"id": "link001", "url": "https://example.invalid/article"}).media == []
