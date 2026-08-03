import requests
from lxml import html
import urllib3
urllib3.disable_warnings()
url = 'https://m.stock.naver.com/marketindex/metals/M04020000'
r = requests.get(url, verify=False)
tree = html.fromstring(r.content)
element = tree.xpath('//*[@id=\"content\"]/div[1]/div[2]/div[2]/strong')
if element:
    print('Found price:', element[0].text_content().strip())
else:
    print('Not found with xpath. DOM classes:', tree.xpath('//strong/@class'))
