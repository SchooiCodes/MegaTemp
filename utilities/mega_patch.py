from utilities.hashcash import solve_hashcash_challenge
from mega.errors import RequestError


def _patch_api_request(original_method):
    def wrapper(self, data):
        import json
        import requests

        params = {'id': self.sequence_num}
        self.sequence_num += 1
        if self.sid:
            params.update({'sid': self.sid})
        if not isinstance(data, list):
            data = [data]

        url = f'{self.schema}://g.api.{self.domain}/cs'
        response = requests.post(
            url, params=params, data=json.dumps(data), timeout=self.timeout,
        )

        if response.status_code == 402:
            hc_header = response.headers.get('X-Hashcash')
            if not hc_header:
                raise RequestError("HTTP 402 without X-Hashcash header")
            solution = solve_hashcash_challenge(hc_header)
            token = hc_header.split(':', 3)[3]
            headers = {'X-Hashcash': f'1:{token}:{solution}'}
            response = requests.post(
                url, params=params, headers=headers,
                data=json.dumps(data), timeout=self.timeout,
            )

        json_resp = json.loads(response.text)
        try:
            if isinstance(json_resp, list):
                int_resp = json_resp[0] if isinstance(json_resp[0], int) else None
            elif isinstance(json_resp, int):
                int_resp = json_resp
            else:
                int_resp = None
        except (IndexError, TypeError):
            int_resp = None

        if int_resp is not None:
            if int_resp == -3:
                raise RuntimeError("Request failed, retrying")
            raise RequestError(int_resp, response.status_code)
        return json_resp[0]

    return wrapper


def patch_mega():
    from mega import Mega
    Mega._api_request = _patch_api_request(Mega._api_request)
