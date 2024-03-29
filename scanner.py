
class Scanner:

    def __init__(self, config, scan_params):
        self.config = config
        self.scan_params = scan_params

    async def scan(self) -> list:
        pass

    def get_post_message(self, p : dict) -> str:
        pass

    def mark_post_as_notified(self, post_id : str):
        pass

    def mark_post_as_interested(self, post_id : str, interested : bool):
        pass

    def get_unmarked_posts(self, date_str : str):
        pass

    def get_interested_posts(self, date = "1970-01-01 00:00:00"):
        pass