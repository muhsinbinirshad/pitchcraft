"""WordprocessingML namespaces and small helpers."""

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
XML_NS = "http://www.w3.org/XML/1998/namespace"

NS = {"w": W_NS, "w14": W14_NS}


def w(tag: str) -> str:
    """Qualified name for a w: tag, e.g. w('p') -> '{ns}p'."""
    return f"{{{W_NS}}}{tag}"


def w14(tag: str) -> str:
    return f"{{{W14_NS}}}{tag}"


XML_SPACE = f"{{{XML_NS}}}space"
