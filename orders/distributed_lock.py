import uuid
import redis

redis_client = redis.Redis(
    host="127.0.0.1",
    port=6379,
    db=0,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


class DistributedLock:
    def __init__(self, name: str, timeout: int = 60):
        self.key     = f"lock:{name}"
        self.timeout = timeout
        self.token   = str(uuid.uuid4())  # unique لكل عملية acquire

    def acquire(self) -> bool:
        """
        حاول تاخذ القفل (بدون انتظار).
        True  = القفل أخذناه، نقدر نكمل.
        False = سيرفر ثاني شايل القفل هلق.
        """
        result = redis_client.set(
            self.key,
            self.token,
            nx=True,          # NX = set only if NOT exists
            ex=self.timeout,  # EX = auto-expire
        )
        return result is True

    def release(self) -> None:
        
        lua = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        end
        return 0
        """
        redis_client.eval(lua, 1, self.key, self.token)

    def ttl(self) -> int:
        """كم ثانية باقية قبل ما القفل ينتهي تلقائياً."""
        return redis_client.ttl(self.key)