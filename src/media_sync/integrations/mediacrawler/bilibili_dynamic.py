"""Original, bounded Bili dynamic protocol parsing; no network or upstream imports.

Protocol references are pinned in docs/executions/0062-bili-dynamic-workflow.
Feed summaries are never promoted to complete OPUS bodies.  Image authority
binds the entire ordered set, not a mutable position or a numeric video ID.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit

BILI_DYNAMIC_FIELD = "__media_sync_bili_dynamic_v1"
BILI_DYNAMIC_SOURCE_FIELD = "bili_dynamic_source"
BILI_DYNAMIC_DETAIL_PATH = "/x/polymer/web-dynamic/v1/detail"
BILI_DYNAMIC_DETAIL_FEATURES = (
    "itemOpusStyle,opusBigCover,onlyfansVote,endFooterHidden,decorationCard,onlyfansAssetsV2,ugcDelete"
)
BILI_OPUS_DETAIL_PATH = "/x/polymer/web-dynamic/v1/opus/detail"
BILI_OPUS_DETAIL_FEATURES = (
    "onlyfansVote,onlyfansAssetsV2,decorationCard,htmlNewStyle,ugcDelete,editable,opusPrivateVisible"
)
BILI_DYNAMIC_MAX_IMAGES = 30
BILI_DYNAMIC_MAX_TEXT = 100_000
_MAX_ID = 2**63 - 1
_TYPE = re.compile(r"DYNAMIC_TYPE_[A-Z_]{1,40}\Z", re.ASCII)
_DID = re.compile(r"[1-9][0-9]{0,18}\Z", re.ASCII)
_BVID = re.compile(r"BV[A-Za-z0-9]{10}\Z", re.ASCII)
_IMAGE_PATH = re.compile(r"/bfs/(?:new_dyn|article)/[A-Za-z0-9_-]{1,200}\.(?:jpg|jpeg|png|webp)\Z", re.ASCII)
_IMAGE_HOST = re.compile(r"i[0-2]\.hdslb\.com\Z", re.ASCII)
_SUPPORTED = frozenset({"DYNAMIC_TYPE_WORD", "DYNAMIC_TYPE_DRAW", "DYNAMIC_TYPE_AV"})


class BiliDynamicError(ValueError):
    code = "bili_dynamic_schema_invalid"

    def __init__(self) -> None:
        super().__init__(self.code)


class BiliDynamicUnsupportedError(BiliDynamicError):
    code = "bili_dynamic_unsupported"


class BiliDynamicIdentityError(BiliDynamicError):
    code = "bili_dynamic_identity_mismatch"


def _mapping(value: object, keys: set[str] | None = None) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise BiliDynamicError
    if keys is not None and set(value) != keys:
        raise BiliDynamicError
    return value


def _component(value: object, allowed: set[str]) -> Mapping[str, object]:
    """Do not silently discard a future content-bearing sibling component."""
    result = _mapping(value)
    if set(result) - allowed:
        raise BiliDynamicUnsupportedError
    return result


def _integer(value: object, maximum: int = _MAX_ID) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise BiliDynamicError
    return value


def _did(value: object) -> str:
    if type(value) is not str or _DID.fullmatch(value) is None or int(value) > _MAX_ID:
        raise BiliDynamicError
    return value


def _text(value: object, *, nullable: bool = False) -> str:
    if value is None and nullable:
        return ""
    if type(value) is not str or len(value) > BILI_DYNAMIC_MAX_TEXT:
        raise BiliDynamicError
    if any((ord(char) < 0x20 and char not in "\n\r\t") or ord(char) == 0x7F for char in value):
        raise BiliDynamicError
    return value


def _sequence(value: object, *, maximum: int) -> Sequence[object]:
    if not isinstance(value, (list, tuple)) or len(value) > maximum:
        raise BiliDynamicError
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BiliDynamicIdentity:
    did: str
    dynamic_type: str
    pub_ts: int
    author_mid: int

    def __post_init__(self) -> None:
        _did(self.did)
        if type(self.dynamic_type) is not str or _TYPE.fullmatch(self.dynamic_type) is None:
            raise BiliDynamicError
        _integer(self.pub_ts, 253_402_300_799)
        _integer(self.author_mid)

    def as_mapping(self) -> dict[str, object]:
        return {
            "did": self.did,
            "dynamic_type": self.dynamic_type,
            "pub_ts": self.pub_ts,
            "author_mid": self.author_mid,
        }

    @classmethod
    def from_mapping(cls, value: object) -> BiliDynamicIdentity:
        item = _mapping(value, {"did", "dynamic_type", "pub_ts", "author_mid"})
        return cls(
            _did(item["did"]), _text(item["dynamic_type"]), _integer(item["pub_ts"]), _integer(item["author_mid"])
        )


def parse_dynamic_identity(item: object, creator_id: int) -> BiliDynamicIdentity:
    _integer(creator_id)
    row = _mapping(item)
    author = _mapping(_mapping(row.get("modules")).get("module_author"))
    if author.get("type") != "AUTHOR_TYPE_NORMAL" or author.get("mid") != creator_id:
        raise BiliDynamicIdentityError
    return BiliDynamicIdentity(
        _did(row.get("id_str")), _text(row.get("type")), _integer(author.get("pub_ts")), _integer(author.get("mid"))
    )


def validate_bili_dynamic_image_url(value: object) -> str:
    if (
        type(value) is not str
        or len(value) > 4096
        or any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise BiliDynamicError
    if "\\" in value:
        raise BiliDynamicError
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or _IMAGE_HOST.fullmatch(parsed.hostname) is None
            or parsed.netloc != parsed.hostname
            or parsed.port is not None
            or parsed.fragment
            or "#" in value
            or _IMAGE_PATH.fullmatch(parsed.path) is None
        ):
            raise BiliDynamicError
    except ValueError:
        raise BiliDynamicError from None
    return value


@dataclass(frozen=True, slots=True)
class BiliDynamicImage:
    url: str = field(repr=False)
    width: int
    height: int

    def __post_init__(self) -> None:
        validate_bili_dynamic_image_url(self.url)
        _integer(self.width, 100_000)
        _integer(self.height, 100_000)

    @property
    def identity(self) -> str:
        # CDN host, HTTP/HTTPS and signing query may rotate, the original BFS
        # object path and dimensions must remain identical.
        return _digest({"path": urlsplit(self.url).path, "width": self.width, "height": self.height})

    def as_mapping(self) -> dict[str, object]:
        return {"url": self.url, "width": self.width, "height": self.height, "identity": self.identity}

    @classmethod
    def from_mapping(cls, value: object) -> BiliDynamicImage:
        item = _mapping(value, {"url", "width", "height", "identity"})
        result = cls(validate_bili_dynamic_image_url(item["url"]), _integer(item["width"]), _integer(item["height"]))
        if item["identity"] != result.identity:
            raise BiliDynamicIdentityError
        return result


@dataclass(frozen=True, slots=True)
class BiliDynamicVideo:
    aid: str
    bvid: str

    def __post_init__(self) -> None:
        _did(self.aid)
        if type(self.bvid) is not str or _BVID.fullmatch(self.bvid) is None:
            raise BiliDynamicError

    def as_mapping(self) -> dict[str, object]:
        return {"aid": self.aid, "bvid": self.bvid}

    @classmethod
    def from_mapping(cls, value: object) -> BiliDynamicVideo:
        item = _mapping(value, {"aid", "bvid"})
        return cls(_did(item["aid"]), _text(item["bvid"]))


def bili_dynamic_image_remote_ids(did: str, images: Sequence[BiliDynamicImage]) -> tuple[str, ...]:
    _did(did)
    if len(images) > BILI_DYNAMIC_MAX_IMAGES or any(type(image) is not BiliDynamicImage for image in images):
        raise BiliDynamicError
    identities = tuple(image.identity for image in images)
    return bili_dynamic_image_remote_ids_from_identities(did, identities)


def bili_dynamic_image_remote_ids_from_identities(did: str, identities: Sequence[str]) -> tuple[str, ...]:
    _did(did)
    if (
        not isinstance(identities, (list, tuple))
        or len(identities) > BILI_DYNAMIC_MAX_IMAGES
        or any(type(identity) is not str or re.fullmatch(r"[0-9a-f]{64}", identity) is None for identity in identities)
    ):
        raise BiliDynamicError
    if len(set(identities)) != len(identities):
        raise BiliDynamicError
    fingerprint = _digest({"did": did, "images": identities})
    return tuple(f"dynamic:{did}:image:{position}:{fingerprint}" for position in range(len(identities)))


@dataclass(frozen=True, slots=True)
class BiliDynamicSource:
    identity: BiliDynamicIdentity
    image_identities: tuple[str, ...]
    video_reference: BiliDynamicVideo | None = None

    def __post_init__(self) -> None:
        if type(self.identity) is not BiliDynamicIdentity or type(self.image_identities) is not tuple:
            raise BiliDynamicError
        bili_dynamic_image_remote_ids_from_identities(self.identity.did, self.image_identities)
        if self.identity.dynamic_type not in _SUPPORTED:
            raise BiliDynamicError
        if self.identity.dynamic_type == "DYNAMIC_TYPE_AV":
            if type(self.video_reference) is not BiliDynamicVideo or self.image_identities:
                raise BiliDynamicError
        elif self.video_reference is not None:
            raise BiliDynamicError
        if self.identity.dynamic_type == "DYNAMIC_TYPE_WORD" and self.image_identities:
            raise BiliDynamicError
        if self.identity.dynamic_type == "DYNAMIC_TYPE_DRAW" and not self.image_identities:
            raise BiliDynamicError

    @property
    def image_remote_ids(self) -> tuple[str, ...]:
        return bili_dynamic_image_remote_ids_from_identities(self.identity.did, self.image_identities)

    def as_mapping(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "identity": self.identity.as_mapping(),
            "image_identities": list(self.image_identities),
            "image_remote_ids": list(self.image_remote_ids),
            "video_reference": None if self.video_reference is None else self.video_reference.as_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: object) -> BiliDynamicSource:
        item = _mapping(
            value, {"schema_version", "identity", "image_identities", "image_remote_ids", "video_reference"}
        )
        if type(item["schema_version"]) is not int or item["schema_version"] != 1:
            raise BiliDynamicError
        identities = tuple(
            _text(entry) for entry in _sequence(item["image_identities"], maximum=BILI_DYNAMIC_MAX_IMAGES)
        )
        result = cls(
            BiliDynamicIdentity.from_mapping(item["identity"]),
            identities,
            None if item["video_reference"] is None else BiliDynamicVideo.from_mapping(item["video_reference"]),
        )
        if tuple(_sequence(item["image_remote_ids"], maximum=BILI_DYNAMIC_MAX_IMAGES)) != result.image_remote_ids:
            raise BiliDynamicIdentityError
        return result


@dataclass(frozen=True, slots=True)
class BiliDynamicPayload:
    identity: BiliDynamicIdentity
    text: str = field(repr=False)
    title: str | None = field(repr=False)
    images: tuple[BiliDynamicImage, ...] = field(default=(), repr=False)
    video_reference: BiliDynamicVideo | None = None

    def __post_init__(self) -> None:
        if type(self.identity) is not BiliDynamicIdentity or self.identity.dynamic_type not in _SUPPORTED:
            raise BiliDynamicError
        _text(self.text)
        if self.title is not None:
            _text(self.title)
        if type(self.images) is not tuple:
            raise BiliDynamicError
        bili_dynamic_image_remote_ids(self.identity.did, self.images)
        if self.identity.dynamic_type == "DYNAMIC_TYPE_AV":
            if type(self.video_reference) is not BiliDynamicVideo or self.images:
                raise BiliDynamicError
        elif self.video_reference is not None:
            raise BiliDynamicError
        if self.identity.dynamic_type == "DYNAMIC_TYPE_WORD" and self.images:
            raise BiliDynamicError
        if self.identity.dynamic_type == "DYNAMIC_TYPE_DRAW" and not self.images:
            raise BiliDynamicError

    def as_mapping(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "identity": self.identity.as_mapping(),
            "text": self.text,
            "title": self.title,
            "images": [image.as_mapping() for image in self.images],
            "video_reference": None if self.video_reference is None else self.video_reference.as_mapping(),
        }

    @classmethod
    def from_mapping(cls, value: object) -> BiliDynamicPayload:
        item = _mapping(value, {"schema_version", "identity", "text", "title", "images", "video_reference"})
        if type(item["schema_version"]) is not int or item["schema_version"] != 1:
            raise BiliDynamicError
        return cls(
            BiliDynamicIdentity.from_mapping(item["identity"]),
            _text(item["text"]),
            None if item["title"] is None else _text(item["title"]),
            tuple(
                BiliDynamicImage.from_mapping(image)
                for image in _sequence(item["images"], maximum=BILI_DYNAMIC_MAX_IMAGES)
            ),
            None if item["video_reference"] is None else BiliDynamicVideo.from_mapping(item["video_reference"]),
        )

    def source_mapping(self) -> dict[str, object]:
        return BiliDynamicSource(
            self.identity,
            tuple(image.identity for image in self.images),
            self.video_reference,
        ).as_mapping()

    def to_record(self) -> dict[str, object]:
        return {
            "dynamic_id": self.identity.did,
            "text": self.text,
            "pub_ts": self.identity.pub_ts,
            "type": self.identity.dynamic_type,
            BILI_DYNAMIC_FIELD: self.as_mapping(),
        }


def _images(value: object, *, key: str) -> tuple[BiliDynamicImage, ...]:
    images = []
    for raw in _sequence(value, maximum=BILI_DYNAMIC_MAX_IMAGES):
        item = _mapping(raw)
        if item.get("live_url") is not None:
            raise BiliDynamicUnsupportedError
        images.append(
            BiliDynamicImage(
                validate_bili_dynamic_image_url(item.get(key)),
                _integer(item.get("width")),
                _integer(item.get("height")),
            )
        )
    return tuple(images)


def _opus_content(item: object, identity: BiliDynamicIdentity) -> tuple[str, str | None, tuple[BiliDynamicImage, ...]]:
    opus = _mapping(item)
    if _did(opus.get("id_str")) != identity.did or _mapping(opus.get("basic")).get("uid") != identity.author_mid:
        raise BiliDynamicIdentityError
    basic = _mapping(opus.get("basic"))
    if (
        type(basic.get("uid")) is not int
        or type(basic.get("comment_type")) is not int
        or basic.get("comment_type") not in {11, 17}
        or opus.get("fallback")
    ):
        raise BiliDynamicUnsupportedError
    text_parts: list[str] = []
    images: list[BiliDynamicImage] = []
    title: str | None = None
    seen: set[str] = set()
    for raw_module in _sequence(opus.get("modules"), maximum=30):
        module = _mapping(raw_module)
        module_type = module.get("module_type")
        if type(module_type) is not str or module_type in seen:
            raise BiliDynamicError
        seen.add(module_type)
        module_key = {
            "MODULE_TYPE_TITLE": "module_title",
            "MODULE_TYPE_AUTHOR": "module_author",
            "MODULE_TYPE_CONTENT": "module_content",
            "MODULE_TYPE_STAT": "module_stat",
            "MODULE_TYPE_EXTEND": "module_extend",
            "MODULE_TYPE_BOTTOM": "module_bottom",
        }.get(module_type)
        if module_key is None:
            raise BiliDynamicUnsupportedError
        _component(module, {"module_type", module_key})
        if module_type == "MODULE_TYPE_TITLE":
            title = _text(_mapping(module.get("module_title")).get("text"))
        elif module_type == "MODULE_TYPE_AUTHOR":
            author = _mapping(module.get("module_author"))
            if (
                type(author.get("mid")) is not int
                or author["mid"] != identity.author_mid
                or type(author.get("pub_ts")) is not int
                or author.get("pub_ts") != identity.pub_ts
            ):
                raise BiliDynamicIdentityError
        elif module_type == "MODULE_TYPE_CONTENT":
            content = _component(module.get("module_content"), {"paragraphs"})
            for raw_paragraph in _sequence(content.get("paragraphs"), maximum=1000):
                paragraph = _mapping(raw_paragraph)
                if type(paragraph.get("para_type")) is not int:
                    raise BiliDynamicError
                if paragraph["para_type"] == 1:
                    _component(paragraph, {"para_type", "align", "text"})
                    pieces = []
                    text = _component(paragraph.get("text"), {"nodes"})
                    for raw_node in _sequence(text.get("nodes"), maximum=1000):
                        node = _mapping(raw_node)
                        if node.get("type") == "TEXT_NODE_TYPE_WORD":
                            _component(node, {"type", "word"})
                            pieces.append(_text(_mapping(node.get("word")).get("words")))
                        elif node.get("type") == "TEXT_NODE_TYPE_RICH":
                            _component(node, {"type", "rich"})
                            pieces.append(_text(_mapping(node.get("rich")).get("text")))
                        else:
                            raise BiliDynamicUnsupportedError
                    text_parts.append("".join(pieces))
                elif paragraph["para_type"] == 2:
                    _component(paragraph, {"para_type", "align", "pic"})
                    images.extend(_images(_component(paragraph.get("pic"), {"pics"}).get("pics"), key="url"))
                else:
                    raise BiliDynamicUnsupportedError
        elif module_type not in {"MODULE_TYPE_STAT", "MODULE_TYPE_EXTEND", "MODULE_TYPE_BOTTOM"}:
            raise BiliDynamicUnsupportedError
    if not {"MODULE_TYPE_AUTHOR", "MODULE_TYPE_CONTENT"} <= seen:
        raise BiliDynamicError
    return _text("\n\n".join(text_parts)), title, tuple(images)


def parse_bili_dynamic_detail(
    item: object,
    *,
    creator_id: int,
    expected_identity: BiliDynamicIdentity | None = None,
    opus_item: object | None = None,
) -> BiliDynamicPayload:
    row = _mapping(item)
    identity = parse_dynamic_identity(row, creator_id)
    if expected_identity is not None and (
        type(expected_identity) is not BiliDynamicIdentity or expected_identity != identity
    ):
        raise BiliDynamicIdentityError
    if identity.dynamic_type not in _SUPPORTED or row.get("orig") is not None or row.get("visible") is not True:
        raise BiliDynamicUnsupportedError
    dynamic = _mapping(_mapping(row.get("modules")).get("module_dynamic"))
    if set(dynamic) - {"desc", "major", "additional", "topic"} or dynamic.get("additional") is not None:
        raise BiliDynamicUnsupportedError
    desc = dynamic.get("desc")
    body = "" if desc is None else _text(_mapping(desc).get("text"))
    major_raw = dynamic.get("major")
    if major_raw is None and identity.dynamic_type == "DYNAMIC_TYPE_WORD":
        if opus_item is not None or desc is None:
            raise BiliDynamicError
        return BiliDynamicPayload(identity, body, None)
    major = _mapping(major_raw)
    major_type = major.get("type")
    major_key = {"MAJOR_TYPE_OPUS": "opus", "MAJOR_TYPE_DRAW": "draw", "MAJOR_TYPE_ARCHIVE": "archive"}.get(
        major_type if type(major_type) is str else ""
    )
    if major_key is None:
        raise BiliDynamicUnsupportedError
    _component(major, {"type", major_key})
    if major_type == "MAJOR_TYPE_OPUS" and identity.dynamic_type in {"DYNAMIC_TYPE_WORD", "DYNAMIC_TYPE_DRAW"}:
        if opus_item is None:
            raise BiliDynamicUnsupportedError
        _mapping(major.get("opus"))
        text, title, images = _opus_content(opus_item, identity)
        return BiliDynamicPayload(identity, text, title, images)
    if opus_item is not None:
        raise BiliDynamicError
    if major_type == "MAJOR_TYPE_DRAW" and identity.dynamic_type == "DYNAMIC_TYPE_DRAW":
        return BiliDynamicPayload(identity, body, None, _images(_mapping(major.get("draw")).get("items"), key="src"))
    if major_type == "MAJOR_TYPE_ARCHIVE" and identity.dynamic_type == "DYNAMIC_TYPE_AV":
        archive = _mapping(major.get("archive"))
        if type(archive.get("type")) is not int or archive["type"] != 1:
            raise BiliDynamicUnsupportedError
        video = BiliDynamicVideo(_did(archive.get("aid")), _text(archive.get("bvid")))
        return BiliDynamicPayload(identity, body, _text(archive.get("title")), video_reference=video)
    raise BiliDynamicUnsupportedError
