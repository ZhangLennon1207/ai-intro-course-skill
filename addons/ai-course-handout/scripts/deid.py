"""Pattern-based redaction helpers; names must be supplied for the current project.

These checks do not prove that a document is anonymous. Review semantic context,
notes and hidden content before distributing a student-facing artifact.
"""
from __future__ import annotations
import re

MASK = "***"
TEACHERS = ()
TEACHER_FILE_TOKENS = ()
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
MEETING_RE = re.compile(r"(?<!\d)\d{3}[-\s]\d{4}[-\s]\d{4}(?!\d)")
ROLE_RE = re.compile(r"(主讲人|授课教师|出卷人|命题人|审核人|整理人|编制人)\s*[:：]\s*([^\s，。；、|｜]{1,12})")
BIB_HINT = re.compile(r"主编|副主编|编著|著者")


def configure(names=()):
    global TEACHERS, TEACHER_FILE_TOKENS
    TEACHERS = tuple(str(name).strip() for name in names if str(name).strip())
    TEACHER_FILE_TOKENS = TEACHERS


def scrub_text(value):
    if not value:
        return value
    out = str(value)
    for name in TEACHERS:
        out = out.replace(name, MASK)
    out = ROLE_RE.sub(lambda match: match.group(1) + "：" + MASK, out)
    for pattern in (EMAIL_RE, PHONE_RE, MEETING_RE):
        out = pattern.sub(MASK, out)
    return out


def clean_filename(value):
    out = str(value or "")
    for name in TEACHER_FILE_TOKENS:
        for separator in ("-", "_", "—"):
            out = out.replace(separator + name, "").replace(name + separator, "")
        out = out.replace(name, "")
    return scrub_text(out)


def scrub_sources(sources):
    return [scrub_text(clean_filename(source)) for source in sources or []]


def scan(text, bibliography_ok=True):
    hits = []
    for name in TEACHERS:
        for match in re.finditer(re.escape(name), str(text or "")):
            if not bibliography_ok or not BIB_HINT.search(text[max(0, match.start()-15):match.end()+15]):
                hits.append(("teacher_name", name))
                break
    for kind, pattern in (("email", EMAIL_RE), ("phone", PHONE_RE), ("meeting", MEETING_RE), ("role_name", ROLE_RE)):
        hits.extend((kind, match.group(0)) for match in pattern.finditer(str(text or "")))
    return list(dict.fromkeys(hits))


def set_docx_props(doc, title="", category="教学资料"):
    properties = doc.core_properties
    properties.author = properties.last_modified_by = "课程组"
    properties.comments = properties.keywords = ""
    properties.category = category
    properties.title = properties.subject = scrub_text(title)


def format_hits(hits):
    # A privacy report must not repeat sensitive values into another artifact.
    return "；".join(sorted({str(kind) + "（已隐藏命中内容）" for kind, _ in hits}))
