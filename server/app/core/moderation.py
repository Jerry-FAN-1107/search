"""内容安全：敏感词 DFA 过滤（输入/输出）与 Prompt 注入启发式拦截。

- 敏感词库 = 内置基础词表 + SENSITIVE_WORDS_FILE 指定的外部词库文件（每行一词）。
- 输入命中：抛 ModerationError（路由层转为对用户友好的错误提示）。
- 输出命中：打码后返回（星号替换），并记录告警日志。
- 词库匹配基于 Trie（字典树）逐字扫描，天然规避子串误杀之外的绕过的常见变形需
  配合外部完整词库（如 sensitive-word 项目导出的词表）。
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import settings
from .logging import get_logger

logger = get_logger(__name__)


class ModerationError(ValueError):
    """内容安全拦截异常，message 面向用户可读。"""


# 内置基础敏感词（仅作兜底示例；生产环境必须通过 SENSITIVE_WORDS_FILE 加载完整词库）
_BUILTIN_WORDS = [
    "制造炸弹",
    "自制炸药",
    "冰毒",
    "恐怖主义",
    "恐怖组织",
]

# Prompt 注入启发式规则：命中即拦截
_INJECTION_PATTERNS = [
    re.compile(r"忽略.{0,12}(之前|以上|先前|所有|系统).{0,12}(指令|指示|提示|要求)", re.I),
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|system)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"(越狱|jail\s*break|\bDAN\b|developer\s*mode)", re.I),
    re.compile(r"(输出|重复|泄露|显示|打印).{0,12}(系统提示|提示词|system\s*prompt|初始指令)", re.I),
    re.compile(r"你现在是.{0,24}(没有|不受|无视).{0,8}限制"),
]


class _Trie:
    """极简字典树：支持敏感词检索与打码。"""

    def __init__(self) -> None:
        self.root: dict = {}

    def add(self, word: str) -> None:
        node = self.root
        for ch in word:
            node = node.setdefault(ch, {})
        node["$"] = True

    def search(self, text: str) -> list[str]:
        """返回 text 中命中的敏感词列表（去重）。"""
        found: set[str] = set()
        for i in range(len(text)):
            node = self.root
            j = i
            while j < len(text) and text[j] in node:
                node = node[text[j]]
                j += 1
                if node.get("$"):
                    found.add(text[i:j])
        return list(found)

    def mask(self, text: str) -> str:
        """将命中的敏感词替换为等长星号。"""
        chars = list(text)
        for i in range(len(text)):
            node = self.root
            j = i
            while j < len(text) and text[j] in node:
                node = node[text[j]]
                j += 1
                if node.get("$"):
                    for k in range(i, j):
                        chars[k] = "*"
        return "".join(chars)


_filter: _Trie | None = None


def _get_filter() -> _Trie:
    """惰性加载敏感词库（内置词 + 外部词库文件）。"""
    global _filter
    if _filter is not None:
        return _filter
    trie = _Trie()
    for w in _BUILTIN_WORDS:
        trie.add(w.strip())
    path = Path(settings.SENSITIVE_WORDS_FILE)
    if path.exists():
        count = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            word = line.strip()
            if word and not word.startswith("#"):
                trie.add(word)
                count += 1
        logger.info("moderation: loaded %d words from %s", count, path)
    else:
        logger.warning("moderation: %s 不存在，仅使用内置基础词表", path)
    _filter = trie
    return trie


def filter_input(text: str) -> None:
    """用户输入安检：Prompt 注入启发式 + 敏感词。命中即抛 ModerationError。"""
    if not settings.CONTENT_MODERATION_ENABLED:
        return
    if settings.PROMPT_INJECTION_GUARD:
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning("moderation: prompt injection blocked, pattern=%s", pattern.pattern)
                raise ModerationError("输入包含疑似提示词注入内容，已被安全策略拦截")
    hits = _get_filter().search(text)
    if hits:
        logger.warning("moderation: input blocked, hits=%d", len(hits))
        raise ModerationError("输入包含违规内容，已被安全策略拦截")


def filter_output(text: str) -> str:
    """模型输出安检：命中敏感词打码后返回。"""
    if not settings.CONTENT_MODERATION_ENABLED or not text:
        return text
    masked = _get_filter().mask(text)
    if masked != text:
        logger.warning("moderation: output masked (len=%d)", len(text))
    return masked
