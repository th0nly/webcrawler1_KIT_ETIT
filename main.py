import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, unquote
import os
import time

# 配置参数 大写是惯例
BASE_URL = "https://www.etit.kit.edu/"
START_URL = urljoin(BASE_URL, "vertiefungsrichtungen_master.php")
PDF_ROOT = r"E:\OneDrive - MSFT\.master_data\KIT\SPO2018专业方向"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9"
}
REQUEST_DELAY = 1  # 请求间隔

# 定义目标PDF标题（德语原文）
# 改进后的多语言配置 英文有5个方向是英语的，所以其字段也不一样
TARGET_LINKS = {
    "exemplary": {
        "pattern": re.compile(
            r'^(Exemplarischer\s+Studienplan|Exemplary\s+Curriculum)\b', 
            re.I | re.U
        ),
        "filename": "Exemplary_Curriculum.pdf"
    },
    "individual": {
        "pattern": re.compile(
            r'^(Individueller\s+Studienplan|Individual\s+Study\s+Plan)\b.*(ab WS 2018/19|starting from winter semester 2018/19)',
            re.I | re.U
        ),
        "filename": "Individual_Study_Plan.pdf"
    },
    "elective": {
        "pattern": re.compile(
            r'^(Empfohlene\s+Wahlmodule|Recommended\s+Elective\s+Modules)\b',
            re.I | re.U
        ),
        "filename": "Recommended_Elective_Modules.pdf"
    }
}

def create_directory(dir_path):
    """创建存储目录"""
    try:
        os.makedirs(dir_path, exist_ok=True)
        print(f"创建目录：{dir_path}")
    except Exception as e:
        print(f"目录创建失败：{str(e)}")
        return False
    return True

def get_final_pdf_url(link_url):
    """获取最终PDF地址（处理重定向）"""
    try:
        with requests.Session() as session:
            response = session.head(link_url, headers=HEADERS, allow_redirects=True, timeout=10)
            response.raise_for_status()
            return response.url
    except Exception as e:
        print(f"解析PDF地址失败：{str(e)}")
        return None

# 专业层， 第二层
def process_direction(direction_url, dir_number):
    """处理单个专业方向"""
    print(f"\n{'='*40}\n正在处理方向：{dir_number}")
    
    try:

        # === 关键修改2：添加专业名字 ====
        # 我修改了顺序，先进入了专业的页面，在提取h1头标题，再创建文件夹
        # 获取方向页面
        response = requests.get(direction_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        h1_tag = soup.find('h1')
        dir_name = h1_tag.get_text().split(':')[-1].strip() if h1_tag else f"Unnamed_{dir_number}"

        # 创建存储目录
        dir_path = os.path.join(PDF_ROOT, f"vertiefungsrichtung_{dir_number}_{dir_name}")
        if not create_directory(dir_path):
            return
        # ===============================

        # 查找所有包含PDF的链接
        pdf_links = {}
        for a_tag in soup.find_all('a', href=True):
            link_text = a_tag.get_text(strip=True)
            for key, config in TARGET_LINKS.items():
                if config["pattern"].search(link_text):
                    # 获取原始链接
                    raw_link = urljoin(direction_url, a_tag['href'])
                    # 获取最终PDF地址
                    pdf_url = get_final_pdf_url(raw_link)
                    if pdf_url and pdf_url.lower().endswith('.pdf'):
                        pdf_links[key] = {
                            "url": pdf_url,
                            "filename": config["filename"]
                        }
                    break

        # 下载所有找到的PDF
        download_count = 0
        for key, data in pdf_links.items():
            file_path = os.path.join(dir_path, data["filename"])
            if os.path.exists(file_path):
                print(f"文件已存在：{data['filename']}")
                continue

            print(f"正在下载：{data['filename']}")
            # 跳转层, 第三层，就是pdf的php链接和对应链接不符合
            try:
                response = requests.get(data["url"], headers=HEADERS)
                response.raise_for_status()
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                download_count += 1
                time.sleep(REQUEST_DELAY)
            except Exception as e:
                print(f"下载失败：{str(e)}")

        print(f"完成下载：{download_count}/3 个文件")

    except Exception as e:
        print(f"处理方向时发生错误：{str(e)}")

# 主页层。第一层
# 这个还在主页面，而添加专业的名字到文件夹需要进入方向内，用h1确定页面的主标题，才能提取出来，所以得在进图专业页面之后进行也就不是这里
# 整个文件的两层也就是三格个response，多了就冗余了。一个在主界面，一个在专业界面，一个负责找到pdf文件之后重定向
def get_direction_links():
    """获取所有专业方向页面链接"""
    print("正在解析主页面...")
    try:
        # 获取所有方向链接
        response = requests.get(START_URL, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 匹配所有vertiefungsrichtung_数字.php的链接
        direction_links = []
        #加上, re.I表示不管大小写。因为方向25是后面加上去的其href为Vertiefungsrichtung_25。傻逼KIT属实不严谨
        pattern = re.compile(r'vertiefungsrichtung_(\d+)\.php', re.I)      
        for a_tag in soup.find_all('a', href=pattern):
            full_url = urljoin(BASE_URL, a_tag['href'])
            match = pattern.search(full_url)
            if match:
                direction_links.append( (full_url, match.group(1)) )  # (URL, 编号)。 group(1)：第一个捕获组内容（即 \d+ 匹配的数字）

        # === 关键修改：有序去重 ===
        seen = set()
        unique_links = []
        for link in direction_links:
            # 用URL作为唯一标识
            if link[0] not in seen:  # link[0] 是完整URL
                seen.add(link[0])
                unique_links.append(link)
        direction_links = unique_links
        # =========================

        # direction_links = list(set(direction_links))  # 去重
        # 这个是无序去重，所以用上面的。
        return direction_links 

    except Exception as e:
        print(f"获取方向列表失败: {str(e)}")
        return []

def main():
    try:
        direction_links = get_direction_links()
        total = len(direction_links)
        print(f"找到 {total} 个专业方向")

        # 遍历处理每个方向
        for idx, (url, number) in enumerate(direction_links, 1):
            print(f"\n▶ 进度：{idx}/{total}")
            process_direction(url, number)

        print("\n✅ 所有方向处理完成！")

    except Exception as e:
        print(f"主流程错误：{str(e)}")

if __name__ == "__main__":
    main()