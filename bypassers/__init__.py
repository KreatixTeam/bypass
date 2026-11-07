from urllib.parse import urlparse

from . import linkvertise, lootlabs, pastes, shorteners, social, workink
from .util import follow_redirect, guess_destination, make_session

DEAD_HOSTS = {"mendationforc.info", "booo.st", "cety.io"}

_GENERICS = {
    "cuty.io", "adfoc.us", "social-unlock.com", "socialwolvez.com",
    "sub2get.com", "subfinal.com", "unlocknow.net", "mboost.me",
    "paster.so", "paster.gg", "mendationforc.info",
}


def route(url, log=lambda m: None):
    host = (urlparse(url).hostname or "").lower()
    bare = host.lstrip("www.")

    if bare in DEAD_HOSTS:
        raise RuntimeError(f"{bare} is dead/unreachable")
    if bare in lootlabs.LOOT_HOSTS:
        return lootlabs.bypass(url, log)
    if bare in workink.WORKINK_HOSTS:
        return workink.bypass(url, log)
    if bare in linkvertise.LINKVERTISE_HOSTS:
        return linkvertise.bypass(url, log)
    if bare in shorteners.BOOST_HOSTS:
        return shorteners.bypass_boost(url, log)
    if bare in social.SOCIAL_HOSTS:
        return social.SOCIAL_HOSTS[bare](url, log)
    if bare in pastes.PASTE_HOSTS:
        return pastes.PASTE_HOSTS[bare](url, log)
    if bare in SHORTENER_SET:
        return shorteners.bypass(url, log)
    if bare in _GENERICS:
        return social.bypass_generic_social(url, log)
    # last resort: redirect-follow + DOM guess works for most shorteners
    return shorteners.bypass(url, log)


SHORTENER_SET = shorteners.SHORTENER_HOSTS - shorteners.BOOST_HOSTS
