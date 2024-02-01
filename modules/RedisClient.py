import redis


class RedisClient:
    """
    用于初始化redis客户端的连接
    """

    def __init__(self, host, port, password, db):
        # 假设您已经有一个Redis客户端的实例
        redis_client = redis.StrictRedis(
            host=host,
            port=port,
            password=password,
            db=db,
            retry_on_timeout=True
        )

        self.client = redis_client
