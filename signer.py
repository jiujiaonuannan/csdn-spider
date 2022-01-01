import execjs
from urllib.parse import urlparse
import requests
from base64 import b64encode
import hmac
import hashlib


class Signer():
  def __init__(self):
    self.nonce_func = execjs.compile("""
    p = function(e) {
        var t = e || null;
        return null == t && (t = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (function(e) {
            var t = 16 * Math.random() | 0;
            return ("x" === e ? t : 3 & t | 8).toString(16)
        }
        ))),
        t
    }
""")

  def get_path(self, url):
    parse_result = urlparse(url)
    path = f"{parse_result.path}?{parse_result.query}"

    return path

  def gen_signature(self, url, accept, nonce_str, cakey, secrectKey):
    url_path = self.get_path(url)
    data = ""
    data += "GET\n"
    data += f"{accept}\n"
    data += "\n\n\n"
    data += f"x-ca-key:{cakey}\n"
    data += f"x-ca-nonce:{nonce_str}\n"
    data += url_path
    appsecret = f"{secrectKey}".encode('utf-8')  # 秘钥
    message = data.encode('utf-8')
    sign = b64encode(hmac.new(appsecret, message, digestmod=hashlib.sha256).digest()).decode()
    return sign

  def get_html(self, url):
    nonce_str = self.nonce_func.call("p", )
    accept = "application/json, text/plain, */*"
    cakey = "203899271"
    app_secrect = "bK9jk5dBEtjauy6gXL7vZCPJ1fOy076H"
    headers = {
      'sec-ch-ua': '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
      'x-ca-signature-headers': 'x-ca-key,x-ca-nonce',
      'x-ca-signature': self.gen_signature(url, accept, nonce_str, cakey, app_secrect),
      'x-ca-nonce': nonce_str,
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36',
      'Accept': accept,
      'x-ca-key': '203899271',
      'Origin': 'https://bbs.csdn.net',
      'Accept-Encoding': 'gzip, deflate, br',
      'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    resp = requests.get(url, headers=headers)
    return resp.status_code, resp.json()
