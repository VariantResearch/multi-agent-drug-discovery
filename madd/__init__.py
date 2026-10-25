"""MADD package. Standard library only. Network calls happen only
where a workflow asks for them: live model providers over HTTPS
(madd/providers_http.py, used by runs and smoke tests), citation
lookups against public registries (madd/resolve.py), and the local
console server (madd/gui.py, localhost by default)."""
__version__ = "0.1.0"
