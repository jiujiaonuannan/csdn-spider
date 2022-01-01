import hashlib
import hmac
import re
from base64 import b64encode
from urllib.parse import urlparse
import json

import execjs
import requests
from scrapy import Selector
from models import Topic, Answer, Author
from datetime import datetime
from signer import Signer


def get_last_urls():
  # 获取最终需要抓取的url
  urls = []
  rsp = requests.get("https://bbs.csdn.net/")
  sel = Selector(text=rsp.text)
  c_nodes = sel.css("div.el-tree-node .custom-tree-node")
  for index, c_node in enumerate(c_nodes):
    signer = Signer()
    url = f"https://bizapi.csdn.net/community-cloud/v1/homepage/community/by/tag?deviceType=PC&tagId={index + 1}"
    code, re_json = signer.get_html(url)
    if code != 200:
      raise Exception("反爬了")
    if "data" in re_json:
      for item in re_json["data"]:
        url = f'{item["url"]}?category={item["id"]}'
        urls.append(url)
    break
  return urls


def parse_topic(url):
  # 获取帖子的详情以及回复
  # 重点！！ 学会分析answer可能出现的各种展示状态 找一条回复最多的帖子，然后分析
  rsp = requests.get(url)
  if rsp.status_code != 200:
    raise Exception("获取帖子详情页反爬了")
  sel = Selector(text=rsp.text)
  topic_id = url.split("/")[-1]
  comment_items = sel.css(".comment-item")
  for comment_item in comment_items:
    answer = Answer()

    user_msg = comment_item.css(".comment-main .user-msg")
    comment_msg = comment_item.css(".comment-main .comment-msg")
    user_name = user_msg.css(".name a::text").extract_first()
    comment_time = user_msg.css(".name span::text").extract_first()  # 此处需要处理现实的是 x小时前 x分钟前 x天前 x个月等情况，转换未datetime
    content = comment_msg.css(".msg span").extract_first()  # 这里分别要考虑 1. 正常回复 2. 引用回复 3. 回复中有代码等各种情况
    praise_nums = comment_msg.css("span.my-love.love span.num::text").extract_first()
    if praise_nums:
      answer.praise_nums = int(praise_nums)

    answer.topic_id = topic_id
    answer.content = content
    answer.author = user_name
    answer.create_time = comment_time


def parse_author(url):
  # url = "https://blog.csdn.net/qq_33437675"
  author_id = url.split("/")[-1]
  # 获取用户的详情
  headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0',
  }
  res_text = requests.get(url, headers=headers).text
  user_text = re.search('window.__INITIAL_STATE__=(.*});</script>', res_text, re.IGNORECASE)
  if user_text:
    author = Author()
    data = user_text.group(1)
    data = json.loads(data)
    author.name = author_id
    base_info = data["pageData"]["data"]["baseInfo"]
    author.desc = base_info["seoModule"]["description"]

    interested = []
    if len(base_info["interestModule"]):
      tags = base_info["interestModule"][0]["tags"]
      for tag in tags:
        interested.append(tag["name"])
    author.industry = ",".join(interested)
    if base_info["blogModule"]:
      author.id = base_info["blogModule"]["blogId"]

    if base_info["achievementModule"]["viewCount"]:
      author.click_nums = int(base_info["achievementModule"]["viewCount"].replace(",", ""))
    if base_info["achievementModule"]["rank"]:
      author.rate = int(base_info["achievementModule"]["rank"].replace(",", ""))
    if base_info["achievementModule"]["achievementList"]:
      author.parised_nums = int(base_info["achievementModule"]["achievementList"][0]["variable"].replace(",", ""))
      author.answer_nums = int(base_info["achievementModule"]["achievementList"][1]["variable"].replace(",", ""))
      author.forward_nums = int(base_info["achievementModule"]["achievementList"][2]["variable"].replace(",", ""))
    if base_info["achievementModule"]["originalCount"]:
      author.original_nums = int(base_info["achievementModule"]["originalCount"].replace(",", ""))
    if base_info["achievementModule"]["fansCount"]:
      author.follower_nums = int(base_info["achievementModule"]["fansCount"].replace(",", ""))

    existed_author = Author.select().where(Author.id == author_id)
    if existed_author:
      author.save()
    else:
      author.save(force_insert=True)

    print(data)


def extract_topic(data_list):
  for value in data_list:
    # 解析user和topic入库
    content = value["content"]
    topic = Topic()
    topic.id = content["contentId"]
    topic.title = content["topicTitle"]
    topic.content = content["description"]
    topic.create_time = datetime.strptime(content["createTime"], '%Y-%m-%d %H:%M:%S')
    topic.create_time = datetime.strptime(content["createTime"], '%Y-%m-%d %H:%M:%S')
    topic.answer_nums = content["commentCount"]
    topic.click_nums = content["viewCount"]
    topic.praised_nums = content["diggNum"]
    topic.author = content["username"]

    existed_topics = Topic.select().where(Topic.id == topic.id)
    if existed_topics:
      topic.save()
    else:
      topic.save(force_insert=True)

    # parse_topic(content["url"])
    parse_author(f'https://blog.csdn.net/{content["username"]}')


def parse_list(url):
  # 获取分类下的category列表
  cagetory_rsp = requests.get(url)
  print(cagetory_rsp)
  if cagetory_rsp.status_code != 200:
    raise Exception("反爬了")
  title_search = re.search('window.__INITIAL_STATE__=(.*});</script>', cagetory_rsp.text, re.IGNORECASE)
  from urllib.parse import urlparse, parse_qs

  o = urlparse(url)
  query = parse_qs(o.query)
  cate_id = query["category"][0]
  next_page = 1
  page_size = 15
  tabid = 0
  total_pages = 1
  if title_search:
    data = title_search.group(1)
    import json
    data = json.loads(data)
    total = data["pageData"]["data"]["baseInfo"]["page"]["total"]
    current_page = data["pageData"]["data"]["baseInfo"]["page"]["currentPage"]
    page_size = data["pageData"]["data"]["baseInfo"]["page"]["pageSize"]
    tabid = data["pageData"]["data"]["baseInfo"]["defaultActiveTab"]
    if total % page_size > 0:
      total_pages = total / page_size + 1
    else:
      total_pages = total / page_size
    #
    # extract_topic(data["pageData"]["data"]["baseInfo"]["dataList"])
    next_page = current_page + 1

  # while next_page < total_pages:
  #   # 注意这里的参数顺序，一定要按照ascii编码排序！！！！！
  #   url = f"https://bizapi.csdn.net/community-cloud/v1/community/listV2?communityId={cate_id}&noMore=false&page={next_page}&pageSize={page_size}&tabId={tabid}&type=1&viewType=0"
  #   signer = Signer()
  #   code, re_json = signer.get_html(url)
  #   if code != 200:
  #     raise Exception("获取下一页反爬了")
  #   extract_topic(re_json["data"]["dataList"][0:2])


if __name__ == '__main__':
  urls = get_last_urls()
  for url in urls[0:10]:
    parse_list(url)
