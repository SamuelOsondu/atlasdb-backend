from slowapi import Limiter
from slowapi.util import get_remote_address

# For multi-replica production deployments, configure storage_uri=settings.REDIS_URL
# so rate limit state is shared across all API instances.
limiter = Limiter(key_func=get_remote_address)
