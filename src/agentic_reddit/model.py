"""Typed Reddit output objects and pure Listing-data normalizers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import urlsplit

_REDDIT_BASE = "https://www.reddit.com"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    """Serialize a datetime as ISO-8601 UTC with a ``Z`` suffix."""
    if value is None:
        return None
    return _utc(value).isoformat().replace("+00:00", "Z")


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _boolean(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _optional_boolean(value: object) -> bool | None:
    """Return an upstream boolean unchanged, or null for absent or malformed values."""
    return value if isinstance(value, bool) else None


def _id(value: object, prefix: str) -> str:
    text = _text(value)
    return text[len(prefix) :] if text.startswith(prefix) else text


def _fullname(raw: dict[str, Any], prefix: str, identifier: str) -> str:
    name = _text(raw.get("name"))
    return name if name.startswith(prefix) else f"{prefix}{identifier}"


def _reddit_url(value: object) -> str:
    url = _text(value)
    if not url:
        return ""
    if url.startswith("/"):
        return f"{_REDDIT_BASE}{url}"
    return url


@dataclass
class Media:
    kind: str
    url: str
    width: int | None
    height: int | None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "url": self.url, "width": self.width, "height": self.height}


@dataclass
class Post:
    id: str
    fullname: str
    url: str
    link_url: str | None
    subreddit: str
    subreddit_prefixed: str
    author: str
    author_fullname: str | None
    title: str
    text: str
    created_at: datetime | None
    edited_at: datetime | None
    score: int | None
    upvote_ratio: int | float | None
    num_comments: int | None
    num_crossposts: int | None
    over_18: bool | None
    spoiler: bool
    is_self: bool
    is_video: bool
    is_original_content: bool
    stickied: bool
    pinned: bool
    locked: bool
    distinguished: str | None
    flair: str | None
    domain: str | None
    thumbnail: str | None
    media: list[Media]
    total_awards: int | None
    removed: str | None
    captured_at: datetime
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fullname": self.fullname,
            "url": self.url,
            "link_url": self.link_url,
            "subreddit": self.subreddit,
            "subreddit_prefixed": self.subreddit_prefixed,
            "author": self.author,
            "author_fullname": self.author_fullname,
            "title": self.title,
            "text": self.text,
            "created_at": _iso(self.created_at),
            "edited_at": _iso(self.edited_at),
            "score": self.score,
            "upvote_ratio": self.upvote_ratio,
            "num_comments": self.num_comments,
            "num_crossposts": self.num_crossposts,
            "over_18": self.over_18,
            "spoiler": self.spoiler,
            "is_self": self.is_self,
            "is_video": self.is_video,
            "is_original_content": self.is_original_content,
            "stickied": self.stickied,
            "pinned": self.pinned,
            "locked": self.locked,
            "distinguished": self.distinguished,
            "flair": self.flair,
            "domain": self.domain,
            "thumbnail": self.thumbnail,
            "media": [item.to_dict() for item in self.media],
            "total_awards": self.total_awards,
            "removed": self.removed,
            "captured_at": _iso(self.captured_at),
            **({"raw": self.raw} if self.raw is not None else {}),
        }


@dataclass
class Comment:
    id: str
    fullname: str
    permalink: str
    post_id: str
    subreddit: str
    parent_id: str
    author: str
    author_fullname: str | None
    text: str
    created_at: datetime | None
    edited_at: datetime | None
    score: int | None
    depth: int | None
    is_submitter: bool
    stickied: bool
    distinguished: str | None
    controversiality: int | None
    collapsed: bool
    score_hidden: bool
    total_awards: int | None
    replies: list[Comment]
    more_count: int | None
    captured_at: datetime
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fullname": self.fullname,
            "permalink": self.permalink,
            "post_id": self.post_id,
            "subreddit": self.subreddit,
            "parent_id": self.parent_id,
            "author": self.author,
            "author_fullname": self.author_fullname,
            "text": self.text,
            "created_at": _iso(self.created_at),
            "edited_at": _iso(self.edited_at),
            "score": self.score,
            "depth": self.depth,
            "is_submitter": self.is_submitter,
            "stickied": self.stickied,
            "distinguished": self.distinguished,
            "controversiality": self.controversiality,
            "collapsed": self.collapsed,
            "score_hidden": self.score_hidden,
            "total_awards": self.total_awards,
            "replies": [item.to_dict() for item in self.replies],
            "more_count": self.more_count,
            "captured_at": _iso(self.captured_at),
            **({"raw": self.raw} if self.raw is not None else {}),
        }


@dataclass
class Subreddit:
    id: str
    fullname: str
    name: str
    prefixed: str
    title: str
    public_description: str
    description: str
    subscribers: int | None
    created_at: datetime | None
    over_18: bool | None
    subreddit_type: str | None
    url: str
    lang: str | None
    icon_url: str | None
    quarantine: bool
    captured_at: datetime
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fullname": self.fullname,
            "name": self.name,
            "prefixed": self.prefixed,
            "title": self.title,
            "public_description": self.public_description,
            "description": self.description,
            "subscribers": self.subscribers,
            "created_at": _iso(self.created_at),
            "over_18": self.over_18,
            "subreddit_type": self.subreddit_type,
            "url": self.url,
            "lang": self.lang,
            "icon_url": self.icon_url,
            "quarantine": self.quarantine,
            "captured_at": _iso(self.captured_at),
            **({"raw": self.raw} if self.raw is not None else {}),
        }


@dataclass
class User:
    id: str
    fullname: str
    name: str
    created_at: datetime | None
    link_karma: int | None
    comment_karma: int | None
    total_karma: int | None
    is_gold: bool
    is_mod: bool
    is_employee: bool
    verified: bool
    has_verified_email: bool
    icon_url: str | None
    accept_followers: bool
    captured_at: datetime
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fullname": self.fullname,
            "name": self.name,
            "created_at": _iso(self.created_at),
            "link_karma": self.link_karma,
            "comment_karma": self.comment_karma,
            "total_karma": self.total_karma,
            "is_gold": self.is_gold,
            "is_mod": self.is_mod,
            "is_employee": self.is_employee,
            "verified": self.verified,
            "has_verified_email": self.has_verified_email,
            "icon_url": self.icon_url,
            "accept_followers": self.accept_followers,
            "captured_at": _iso(self.captured_at),
            **({"raw": self.raw} if self.raw is not None else {}),
        }


def _media_url(node: dict[str, Any]) -> str:
    for key in ("url", "fallback_url", "u"):
        url = _text(node.get(key))
        if url:
            return unescape(url)
    return ""


def _safe_external_url(value: object) -> str:
    url = unescape(_text(value))
    parsed = urlsplit(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def build_media(raw_media: dict[str, Any], *, kind: str = "unknown") -> Media:
    """Normalize one Reddit media node into a stable attachment."""
    source = raw_media.get("s") if isinstance(raw_media.get("s"), dict) else raw_media
    url = _media_url(source)
    return Media(
        kind=kind,
        url=url,
        width=_integer(source.get("x") or source.get("width")),
        height=_integer(source.get("y") or source.get("height")),
    )


def _image_media(raw_post: dict[str, Any]) -> Media | None:
    if _text(raw_post.get("post_hint")) != "image":
        return None
    url = _safe_external_url(raw_post.get("url"))
    if not url:
        return None
    preview = raw_post.get("preview")
    images = preview.get("images") if isinstance(preview, dict) else None
    image = images[0] if isinstance(images, list) and images and isinstance(images[0], dict) else {}
    source = image.get("source") if isinstance(image.get("source"), dict) else {}
    return Media(
        kind="image",
        url=url,
        width=_integer(source.get("width")),
        height=_integer(source.get("height")),
    )


def _embed_media(raw_post: dict[str, Any], node: dict[str, Any]) -> Media | None:
    url = _safe_external_url(raw_post.get("url"))
    if not url:
        return None
    return Media(
        kind="embed",
        url=url,
        width=_integer(node.get("width")),
        height=_integer(node.get("height")),
    )


def _post_media(raw_post: dict[str, Any]) -> list[Media]:
    gallery_data = raw_post.get("gallery_data")
    metadata = raw_post.get("media_metadata")
    if isinstance(gallery_data, dict) and isinstance(metadata, dict):
        result = []
        for item in gallery_data.get("items", []):
            media_id = item.get("media_id") if isinstance(item, dict) else None
            media = metadata.get(media_id) if isinstance(media_id, str) else None
            if isinstance(media, dict):
                normalized = build_media(media, kind="gallery")
                if normalized.url:
                    result.append(normalized)
        if result:
            return result
    secure_media = raw_post.get("secure_media")
    media = secure_media if isinstance(secure_media, dict) else raw_post.get("media")
    if isinstance(media, dict):
        reddit_video = media.get("reddit_video")
        if isinstance(reddit_video, dict):
            normalized = build_media(reddit_video, kind="video")
            if normalized.url:
                return [normalized]
        oembed = media.get("oembed")
        if isinstance(oembed, dict):
            normalized = _embed_media(raw_post, oembed)
            if normalized is not None:
                return [normalized]
    embed = raw_post.get("media_embed")
    if isinstance(embed, dict):
        normalized = _embed_media(raw_post, embed)
        if normalized is not None:
            return [normalized]
    image = _image_media(raw_post)
    return [image] if image is not None else []


def _edited(value: object) -> datetime | None:
    return _timestamp(value) if value is not False else None


def build_post(
    raw_post: dict[str, Any], *, captured_at: datetime | None = None, include_raw: bool = False
) -> Post:
    """Normalize one ``t3`` data object."""
    captured = _utc(captured_at) if captured_at is not None else datetime.now(UTC)
    identifier = _id(raw_post.get("id"), "t3_")
    is_self = _boolean(raw_post.get("is_self"))
    outbound = _text(raw_post.get("url"))
    return Post(
        id=identifier,
        fullname=_fullname(raw_post, "t3_", identifier),
        url=_reddit_url(raw_post.get("permalink")),
        link_url=outbound if not is_self else None,
        subreddit=_text(raw_post.get("subreddit")),
        subreddit_prefixed=_text(raw_post.get("subreddit_name_prefixed")),
        author=_text(raw_post.get("author")),
        author_fullname=_text(raw_post.get("author_fullname")) or None,
        title=_text(raw_post.get("title")),
        text=_text(raw_post.get("selftext")),
        created_at=_timestamp(raw_post.get("created_utc")),
        edited_at=_edited(raw_post.get("edited")),
        score=_integer(raw_post.get("score")),
        upvote_ratio=_number(raw_post.get("upvote_ratio")),
        num_comments=_integer(raw_post.get("num_comments")),
        num_crossposts=_integer(raw_post.get("num_crossposts")),
        over_18=_optional_boolean(raw_post.get("over_18")),
        spoiler=_boolean(raw_post.get("spoiler")),
        is_self=is_self,
        is_video=_boolean(raw_post.get("is_video")),
        is_original_content=_boolean(raw_post.get("is_original_content")),
        stickied=_boolean(raw_post.get("stickied")),
        pinned=_boolean(raw_post.get("pinned")),
        locked=_boolean(raw_post.get("locked")),
        distinguished=_text(raw_post.get("distinguished")) or None,
        flair=_text(raw_post.get("link_flair_text")) or None,
        domain=_text(raw_post.get("domain")) or None,
        thumbnail=_text(raw_post.get("thumbnail")) or None,
        media=_post_media(raw_post),
        total_awards=_integer(raw_post.get("total_awards_received")),
        removed=_text(raw_post.get("removed_by_category")) or None,
        captured_at=captured,
        raw=raw_post if include_raw else None,
    )


def _reply_data(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or value.get("kind") != "Listing":
        return []
    data = value.get("data")
    children = data.get("children") if isinstance(data, dict) else None
    return [
        child["data"]
        for child in children or []
        if isinstance(child, dict)
        and child.get("kind") == "t1"
        and isinstance(child.get("data"), dict)
    ]


def _more_count(value: object) -> int | None:
    if not isinstance(value, dict) or value.get("kind") != "Listing":
        return None
    data = value.get("data")
    children = data.get("children") if isinstance(data, dict) else None
    counts = [
        _integer(child.get("data", {}).get("count"))
        for child in children or []
        if isinstance(child, dict)
        and child.get("kind") == "more"
        and isinstance(child.get("data"), dict)
    ]
    counts = [count for count in counts if count is not None]
    return sum(counts) if counts else None


def build_comment(
    raw_comment: dict[str, Any], *, captured_at: datetime | None = None, include_raw: bool = False
) -> Comment:
    """Normalize one ``t1`` data object, including its nested reply Listing."""
    captured = _utc(captured_at) if captured_at is not None else datetime.now(UTC)
    identifier = _id(raw_comment.get("id"), "t1_")
    return Comment(
        id=identifier,
        fullname=_fullname(raw_comment, "t1_", identifier),
        permalink=_reddit_url(raw_comment.get("permalink")),
        post_id=_text(raw_comment.get("link_id")),
        subreddit=_text(raw_comment.get("subreddit")),
        parent_id=_text(raw_comment.get("parent_id")),
        author=_text(raw_comment.get("author")),
        author_fullname=_text(raw_comment.get("author_fullname")) or None,
        text=_text(raw_comment.get("body")),
        created_at=_timestamp(raw_comment.get("created_utc")),
        edited_at=_edited(raw_comment.get("edited")),
        score=_integer(raw_comment.get("score")),
        depth=_integer(raw_comment.get("depth")),
        is_submitter=_boolean(raw_comment.get("is_submitter")),
        stickied=_boolean(raw_comment.get("stickied")),
        distinguished=_text(raw_comment.get("distinguished")) or None,
        controversiality=_integer(raw_comment.get("controversiality")),
        collapsed=_boolean(raw_comment.get("collapsed")),
        score_hidden=_boolean(raw_comment.get("score_hidden")),
        total_awards=_integer(raw_comment.get("total_awards_received")),
        replies=[
            build_comment(item, captured_at=captured, include_raw=include_raw)
            for item in _reply_data(raw_comment.get("replies"))
        ],
        more_count=_more_count(raw_comment.get("replies")),
        captured_at=captured,
        raw=raw_comment if include_raw else None,
    )


def build_subreddit(
    raw_subreddit: dict[str, Any], *, captured_at: datetime | None = None, include_raw: bool = False
) -> Subreddit:
    """Normalize one ``t5`` data object."""
    captured = _utc(captured_at) if captured_at is not None else datetime.now(UTC)
    identifier = _id(raw_subreddit.get("id"), "t5_")
    icon = (
        _text(raw_subreddit.get("community_icon")) or _text(raw_subreddit.get("icon_img")) or None
    )
    return Subreddit(
        id=identifier,
        fullname=_fullname(raw_subreddit, "t5_", identifier),
        name=_text(raw_subreddit.get("display_name")),
        prefixed=_text(raw_subreddit.get("display_name_prefixed")),
        title=_text(raw_subreddit.get("title")),
        public_description=_text(raw_subreddit.get("public_description")),
        description=_text(raw_subreddit.get("description")),
        subscribers=_integer(raw_subreddit.get("subscribers")),
        created_at=_timestamp(raw_subreddit.get("created_utc")),
        over_18=_optional_boolean(raw_subreddit.get("over18")),
        subreddit_type=_text(raw_subreddit.get("subreddit_type")) or None,
        url=_reddit_url(raw_subreddit.get("url")),
        lang=_text(raw_subreddit.get("lang")) or None,
        icon_url=icon,
        quarantine=_boolean(raw_subreddit.get("quarantine")),
        captured_at=captured,
        raw=raw_subreddit if include_raw else None,
    )


def build_user(
    raw_user: dict[str, Any], *, captured_at: datetime | None = None, include_raw: bool = False
) -> User:
    """Normalize one ``t2`` data object or user-about data object."""
    captured = _utc(captured_at) if captured_at is not None else datetime.now(UTC)
    identifier = _id(raw_user.get("id"), "t2_")
    name = _text(raw_user.get("name"))
    if name.startswith("t2_"):
        name = (
            _text(raw_user.get("subreddit", {}).get("display_name"))
            if isinstance(raw_user.get("subreddit"), dict)
            else ""
        )
    icon = _text(raw_user.get("icon_img")) or _text(raw_user.get("snoovatar_img")) or None
    return User(
        id=identifier,
        fullname=_fullname(raw_user, "t2_", identifier),
        name=name,
        created_at=_timestamp(raw_user.get("created_utc")),
        link_karma=_integer(raw_user.get("link_karma")),
        comment_karma=_integer(raw_user.get("comment_karma")),
        total_karma=_integer(raw_user.get("total_karma")),
        is_gold=_boolean(raw_user.get("is_gold")),
        is_mod=_boolean(raw_user.get("is_mod")),
        is_employee=_boolean(raw_user.get("is_employee")),
        verified=_boolean(raw_user.get("verified")),
        has_verified_email=_boolean(raw_user.get("has_verified_email")),
        icon_url=icon,
        accept_followers=_boolean(raw_user.get("accept_followers")),
        captured_at=captured,
        raw=raw_user if include_raw else None,
    )


MEDIA_FIELD_DESCRIPTIONS = {
    "kind": ("string", "One of image | video | gallery | embed | unknown."),
    "url": ("string", "Media URL supplied by Reddit."),
    "width": ("integer | null", "Media width in pixels, or null when unavailable."),
    "height": ("integer | null", "Media height in pixels, or null when unavailable."),
}


COMMON_FIELD_DESCRIPTIONS = {
    "id": "Reddit base-36 identifier without its fullname prefix.",
    "fullname": "Reddit fullname including its thing-type prefix.",
    "author": "Author username, or an empty string when Reddit did not provide one.",
    "author_fullname": "Author t2 fullname, or null when unavailable.",
    "created_at": "UTC creation timestamp, or null when Reddit did not provide a valid timestamp.",
    "edited_at": "UTC edit timestamp, or null when the record was not edited or is invalid.",
    "captured_at": "UTC timestamp when this record was retrieved.",
    "score": "Reddit score, or null when unavailable.",
    "over_18": (
        "Whether Reddit explicitly marked this record as adult content; "
        "null when absent or malformed."
    ),
    "url": "Canonical Reddit URL for this record.",
    "media": "Media attachments associated with this post.",
    "replies": "Nested replies represented as Comment objects.",
}


def _descriptions(keys: list[str], label: str) -> dict[str, tuple[str, str]]:
    descriptions = {
        key: ("string", COMMON_FIELD_DESCRIPTIONS.get(key, f"Normalized {key.replace('_', ' ')}."))
        for key in keys
    }
    descriptions["raw"] = ("object", f"Optional raw {label.lower()} source data.")
    return descriptions


POST_FIELD_DESCRIPTIONS = _descriptions(
    list(
        Post(
            "",
            "",
            "",
            None,
            "",
            "",
            "",
            None,
            "",
            "",
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            None,
            None,
            None,
            None,
            [],
            None,
            None,
            datetime.now(UTC),
        ).to_dict()
    ),
    "Post field",
)
COMMENT_FIELD_DESCRIPTIONS = _descriptions(
    list(
        Comment(
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            None,
            "",
            None,
            None,
            None,
            None,
            False,
            False,
            None,
            None,
            False,
            False,
            None,
            [],
            None,
            datetime.now(UTC),
        ).to_dict()
    ),
    "Comment field",
)
SUBREDDIT_FIELD_DESCRIPTIONS = _descriptions(
    list(
        Subreddit(
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            None,
            None,
            False,
            None,
            "",
            None,
            None,
            False,
            datetime.now(UTC),
        ).to_dict()
    ),
    "Subreddit field",
)
USER_FIELD_DESCRIPTIONS = _descriptions(
    list(
        User(
            "",
            "",
            "",
            None,
            None,
            None,
            None,
            False,
            False,
            False,
            False,
            False,
            None,
            False,
            datetime.now(UTC),
        ).to_dict()
    ),
    "User field",
)

# Refine generic descriptions into JSON-facing types without duplicating serializer key order.
for descriptions, nullable, integers, booleans in (
    (
        POST_FIELD_DESCRIPTIONS,
        {
            "link_url",
            "author_fullname",
            "created_at",
            "edited_at",
            "score",
            "upvote_ratio",
            "num_comments",
            "num_crossposts",
            "over_18",
            "distinguished",
            "flair",
            "domain",
            "thumbnail",
            "total_awards",
            "removed",
        },
        {"score", "num_comments", "num_crossposts", "total_awards"},
        {
            "over_18",
            "spoiler",
            "is_self",
            "is_video",
            "is_original_content",
            "stickied",
            "pinned",
            "locked",
        },
    ),
    (
        COMMENT_FIELD_DESCRIPTIONS,
        {
            "author_fullname",
            "created_at",
            "edited_at",
            "score",
            "depth",
            "distinguished",
            "controversiality",
            "total_awards",
            "more_count",
        },
        {"score", "depth", "controversiality", "total_awards", "more_count"},
        {"is_submitter", "stickied", "collapsed", "score_hidden"},
    ),
    (
        SUBREDDIT_FIELD_DESCRIPTIONS,
        {"subscribers", "created_at", "over_18", "subreddit_type", "lang", "icon_url"},
        {"subscribers"},
        {"over_18", "quarantine"},
    ),
    (
        USER_FIELD_DESCRIPTIONS,
        {"created_at", "link_karma", "comment_karma", "total_karma", "icon_url"},
        {"link_karma", "comment_karma", "total_karma"},
        {"is_gold", "is_mod", "is_employee", "verified", "has_verified_email", "accept_followers"},
    ),
):
    for key in descriptions:
        field_type = "string"
        if key in nullable:
            field_type = (
                "boolean | null"
                if key in booleans
                else "integer | null"
                if key in integers
                else "number | null"
                if key == "upvote_ratio"
                else "string | null"
            )
        elif key in booleans:
            field_type = "boolean"
        elif key == "media":
            field_type = "array<Media>"
        elif key == "replies":
            field_type = "array<Comment>"
        elif key == "raw":
            field_type = "object"
        descriptions[key] = (field_type, descriptions[key][1])


def _schema_fields(
    sample: dict[str, Any], descriptions: dict[str, tuple[str, str]]
) -> list[dict[str, Any]]:
    return [
        {
            "name": key,
            "type": descriptions[key][0],
            "description": descriptions[key][1],
            "always_present": key != "raw",
        }
        for key in sample
    ]


def media_schema_fields() -> list[dict[str, Any]]:
    return _schema_fields(Media("unknown", "", None, None).to_dict(), MEDIA_FIELD_DESCRIPTIONS)


def post_schema_fields() -> list[dict[str, Any]]:
    return _schema_fields(
        Post(
            "",
            "",
            "",
            None,
            "",
            "",
            "",
            None,
            "",
            "",
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            None,
            None,
            None,
            None,
            [],
            None,
            None,
            datetime.now(UTC),
            {},
        ).to_dict(),
        POST_FIELD_DESCRIPTIONS,
    )


def comment_schema_fields() -> list[dict[str, Any]]:
    return _schema_fields(
        Comment(
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            None,
            "",
            None,
            None,
            None,
            None,
            False,
            False,
            None,
            None,
            False,
            False,
            None,
            [],
            None,
            datetime.now(UTC),
            {},
        ).to_dict(),
        COMMENT_FIELD_DESCRIPTIONS,
    )


def subreddit_schema_fields() -> list[dict[str, Any]]:
    return _schema_fields(
        Subreddit(
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            None,
            None,
            False,
            None,
            "",
            None,
            None,
            False,
            datetime.now(UTC),
            {},
        ).to_dict(),
        SUBREDDIT_FIELD_DESCRIPTIONS,
    )


def user_schema_fields() -> list[dict[str, Any]]:
    return _schema_fields(
        User(
            "",
            "",
            "",
            None,
            None,
            None,
            None,
            False,
            False,
            False,
            False,
            False,
            None,
            False,
            datetime.now(UTC),
            {},
        ).to_dict(),
        USER_FIELD_DESCRIPTIONS,
    )


def schema_fields() -> list[dict[str, Any]]:
    """Return Post fields in exactly ``Post.to_dict()`` order."""
    return post_schema_fields()


def _property(field: dict[str, Any]) -> dict[str, Any]:
    types = {
        "string": "string",
        "string | null": ["string", "null"],
        "integer | null": ["integer", "null"],
        "number | null": ["number", "null"],
        "boolean": "boolean",
        "boolean | null": ["boolean", "null"],
        "object": "object",
        "array<object>": "array",
        "array<Media>": "array",
        "array<Comment>": "array",
    }
    prop: dict[str, Any] = {"description": field["description"], "type": types[field["type"]]}
    if field["name"].endswith("_at"):
        prop["format"] = "date-time"
    if field["type"] == "array<object>":
        prop["items"] = {"type": "object"}
    elif field["type"] == "array<Media>":
        prop["items"] = {"$ref": "#/$defs/Media"}
    elif field["type"] == "array<Comment>":
        prop["items"] = {"$ref": "#/$defs/Comment"}
    return prop


def _object_schema(fields: list[dict[str, Any]], description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "description": description,
        "properties": {field["name"]: _property(field) for field in fields},
        "required": [field["name"] for field in fields if field["always_present"]],
        "additionalProperties": False,
    }


def json_schema() -> dict[str, Any]:
    """Return the generated Reddit record schema using JSON Schema draft 2020-12."""
    definitions = {
        "Media": _object_schema(media_schema_fields(), "One Post media attachment."),
        "Comment": _object_schema(comment_schema_fields(), "One threaded Reddit comment."),
        "Subreddit": _object_schema(subreddit_schema_fields(), "One Reddit community."),
        "User": _object_schema(user_schema_fields(), "One Reddit user."),
        "Post": _object_schema(post_schema_fields(), "One Reddit post."),
    }
    definitions["Post"]["properties"]["media"] = {
        "type": "array",
        "items": {"$ref": "#/$defs/Media"},
        "description": POST_FIELD_DESCRIPTIONS["media"][1],
    }
    definitions["Comment"]["properties"]["replies"] = {
        "type": "array",
        "items": {"$ref": "#/$defs/Comment"},
        "description": COMMENT_FIELD_DESCRIPTIONS["replies"][1],
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Reddit record",
        "oneOf": [
            {"$ref": "#/$defs/Post"},
            {"$ref": "#/$defs/Comment"},
            {"$ref": "#/$defs/Subreddit"},
            {"$ref": "#/$defs/User"},
        ],
        "$defs": definitions,
    }
