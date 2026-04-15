import json
import urllib.request
import urllib.error
import urllib.parse  # 用于 URL 编码
import base64        # 用于 Base64 编码
import html
import socket

# ================= 配置区 =================
WINDHAWK_AUTHOR = "Joe Ye"       # ⚠️ 请替换为你的 Windhawk 作者名
GREASYFORK_USER_URL = "https://api.greasyfork.org/zh-CN/users/1460524-joeye-233.json" # 个人主页+.json
WINDHAWK_CATALOG_URL = "https://mods.windhawk.net/catalogs/zh-CN.json" # 这里用 en.json 还是 zh-CN.json 都可以
OUTPUT_FILE = "README.md"
TABLE_COLUMNS = 3              # 每行展示项目数，可改为 2/3/4 等
REQUEST_TIMEOUT = 15           # 超时时间（秒）

IMAGES_REPO_USER = "JoeYe-233"
IMAGES_REPO_NAME = "images"  # 图片仓库名称
IMAGES_REPO_BRANCH = "main"   # 图片仓库分支，通常是 main 或 master

HISTORY_FILE = "history.json" # 用于存储上次的统计数据，生成 Markdown 时对比使用
# ==========================================

# --- 准备 Windhawk 的 SVG 图标 ---
WINDHAWK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 750 750"><path fill="white" d="m208 255 4-1A306 306 0 0 0 70 392c84-46 162-53 178-48 1 0-7 45-36 83-31 40-83 73-83 73q29 3 57 0 50-3 92-34c11-10 32-39 30-35-12 31-14 67-12 100q1 30 9 59 8 24 21 45l8 7c0-1-8-112 48-167 103-100 216-5 216-5s-4-75-89-112c203-18 159 102 159 102s70-29 59-115c-9-77-85-95-100-98-13-22-113-187-280-122-181 71-327 54-327 54q33 37 74 59 55 26 114 17m314-16 19 6q-1 10-10 11-9-1-10-12zm-40 2q0-8 3-14l11 3 11 3-2 11c0 15 12 27 26 27 13 1 23-9 26-22l8 2a42 42 0 0 1-83-10"/></svg>'

# 将 SVG 转换为 Base64 编码，并拼接好前缀
b64_logo = base64.b64encode(WINDHAWK_SVG.encode('utf-8')).decode('utf-8')
WINDHAWK_LOGO_PARAM = urllib.parse.quote(f"data:image/svg+xml;base64,{b64_logo}")

def load_history():
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_history(current_stats):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(current_stats, f, indent=4)

def format_rating(rating_val):
    """将 0-10 的评分转换为 X.X ★ 格式"""
    if not rating_val or rating_val == 0:
        return "暂无评分"
    # 计算星级：10分=5星，9分=4.5星
    stars = rating_val / 2.0
    # 格式化为一位小数，并加上星星符号
    return f"{stars:.1f} ★"

def get_session_with_proxy():
    proxies = urllib.request.getproxies()
    clean_proxies = {}
    for k, v in proxies.items():
        if isinstance(v, str) and v.startswith('https://'):
            clean_proxies[k] = v.replace('https://', 'http://', 1)
        else:
            clean_proxies[k] = v
    if clean_proxies:
        print(f"[*] 检测到系统代理，已配置修正: {clean_proxies}")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(clean_proxies))
        urllib.request.install_opener(opener)
    else:
        print("[*] 未检测到系统代理，直连。")
    return clean_proxies

get_session_with_proxy()

def fetch_json(url):
    """通用的 JSON 获取函数，伪装浏览器 User-Agent 防止被拦截"""
    print(f"正在获取: {url} ...")
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.URLError as e:
        if isinstance(getattr(e, 'reason', None), socket.timeout):
            raise TimeoutError(f"请求超时（>{REQUEST_TIMEOUT}s）") from e
        raise
    except TimeoutError as e:
        raise TimeoutError(f"请求超时（>{REQUEST_TIMEOUT}s）") from e

# --- 新增：获取图片仓库的文件列表 ---
def fetch_image_list():
    url = f"https://api.github.com/repos/{IMAGES_REPO_USER}/{IMAGES_REPO_NAME}/git/trees/{IMAGES_REPO_BRANCH}?recursive=1"
    try:
        data = fetch_json(url)
        # 提取所有文件路径
        files = [item['path'] for item in data.get('tree', []) if item['type'] == 'blob']
        print(f"[*] 成功获取图片仓库列表，共 {len(files)} 个文件。")
        return files
    except Exception as e:
        print(f"[!] 获取图片列表失败，图片功能将被跳过: {e}")
        return []

def find_best_image(mod_id, image_list):
    # 筛选出属于该 mod_id 的所有图片
    matches = [f for f in image_list if f.startswith(f"{mod_id}-") or f.startswith(f"{mod_id}.")]

    if not matches:
        return None

    # 定义优先级打分函数
    def score_image(filename):
        name_lower = filename.lower()
        if 'before-after' in name_lower:
            return 3  # 最优先：同时包含对比
        elif 'after' in name_lower:
            return 2  # 次优先：修改后的效果图
        elif 'before' in name_lower:
            return 0  # 最低优先级：只显示修改前没太大意义
        else:
            return 1  # 默认优先级（比如没有任何后缀的纯截图）

    # 按照分数选出最高分的图片
    best_match = max(matches, key=score_image)

    # 拼接 Raw 链接
    return f"https://raw.githubusercontent.com/{IMAGES_REPO_USER}/{IMAGES_REPO_NAME}/{IMAGES_REPO_BRANCH}/{best_match}"

def escape_shields_text(value):
    """转义 Shields 路径模式中的特殊字符，避免 404（如 2025-04-22）。"""
    text = str(value)
    return text.replace('-', '--').replace('_', '__').replace(' ', '_')

def generate_table(items, platform):
    """通用的排版生成器，将一维数组转换为 N列 HTML 表格（列数可配置）"""
    if not items:
        return "<p>暂无数据</p>\n"

    md = ''
    columns = max(TABLE_COLUMNS, 1)
    cell_width = f"{100 / columns:.2f}%"

    # 每两组（每组为“信息行+链接行”）切一个新表格
    groups_per_table = 1

    # 按每 columns 个一组进行切割
    for i in range(0, len(items), columns):
        if i % (columns * groups_per_table) == 0:
            if i != 0:
                md += "</table>\n\n"
            md += '<table width="100%">\n'

        group = items[i:i + columns]
        if len(group) < columns:
            group.extend([None] * (columns - len(group)))

        # 第一排 (标题、描述、图片、徽章)
        md += "  <tr>\n"
        for item in group:
            md += render_top_cell(item, cell_width, platform)
        md += "  </tr>\n"

        # 第二排 (链接按钮)
        md += "  <tr>\n"
        for item in group:
            md += render_bottom_cell(item, platform)
        md += "  </tr>\n"

    md += "</table>\n"
    return md

def render_top_cell(item, cell_width, platform):
    spacer = ' &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp;'
    
    if not item:
        return f'    <td width="{cell_width}" valign="top">Coming Soon...{spacer}</td>\n'

    # 转义描述中的特殊字符，防止破坏 HTML 表格
    safe_desc = html.escape(item.get('desc', ''))
    badges = build_badges(item, platform)

    img_tag = ""
    if item.get('img_url'):
        # 加入 <a> 标签并设置 target="_blank"
        # 只保留 height，去掉一切可能引起冲突的 width，依靠浏览器原生等比缩放
        img_tag = f'<a href="{item["img_url"]}" target="_blank"><img src="{item["img_url"]}" height="140" alt="{item["name"]}"></a>'

    return f'''    <td width="{cell_width}" valign="top">
      <b>{item['name']}</b><br>
      <sub>{safe_desc}</sub><br>
      <br>
      {badges}<br>
      <br>
      {img_tag}<br>
    </td>\n'''

def build_badges(item, platform):
    """根据平台生成徽章，统一放在第一排信息区。"""
    if platform == "windhawk":
        # 评分徽章
        rating_esc = escape_shields_text(item["rating_text"])
        # 评分颜色：如果是暂无评分用 grey，否则用 gold(黄色) 或 success(绿色)
        r_color = "gold" if item["rating_text"] != "暂无评分" else "grey"
        padding = "%E2%80%8B%20" if item["rating_text"] != "暂无评分" else ""  # 零宽字符阻止trim + 普通空格，增加徽章间距
        badge_rating = f'<img src="https://img.shields.io/badge/评分-{padding}{rating_esc}-{r_color}?style=flat-square">'

        # 日增量徽章
        delta = item["daily"]
        # 保留一位小数，不额外加正号
        delta_text = f"{delta}"
        # 颜色处理：正数绿色/橙色，负数红色，0灰色
        if delta > 0: d_color = "orange"
        elif delta < 0: d_color = "critical"
        else: d_color = "grey"

        badge_daily = f'<img src="https://img.shields.io/badge/日装-{delta_text}-{d_color}?style=flat-square">'

        # 原有的总安装和版本
        badge_users = f'<img src="https://img.shields.io/badge/总安装-{item["users"]}-0078D7?style=flat-square&logo={WINDHAWK_LOGO_PARAM}">'
        version_text = escape_shields_text(f'v{item["version"]}')
        badge_version = f'<img src="https://img.shields.io/badge/版本-{version_text}-00B3D6?style=flat-square">'
        # 你可以根据排版决定怎么组合，比如：
        return f"{badge_users} {badge_version} {badge_daily} {badge_rating}"

    if platform == "greasyfork":
        badge1 = f'<img src="https://img.shields.io/badge/总安装-{item["users"]}-e95757?style=flat-square&logo=tampermonkey">'
        version_text = escape_shields_text(f'v{item["version"]}')
        badge2 = f'<img src="https://img.shields.io/badge/版本-{version_text}-lightgrey?style=flat-square">'
        badge3 = f'<img src="https://img.shields.io/badge/日装-{item["daily"]}-orange?style=flat-square">'
        badge4 = f'<img src="https://img.shields.io/badge/👍 好评-{item["good_ratings"]}-success?style=flat-square">'
        return f"{badge1} {badge2} {badge3} {badge4}" # 回车加<br>即可

    return ""

def render_bottom_cell(item, platform):
    if not item:
        return '    <td valign="bottom">🚧 施工中</td>\n'

    # 徽章放在第一排，这里只保留链接
    link_text = "获 取"
    # 在 a 标签中加入 target="_blank"
    return f'''    <td valign="bottom">
      👉 <a href="{item['url']}" target="_blank">{link_text}</a>
    </td>\n'''# style="text-decoration:none;但是可惜 GitHub 很激进不允许在 Markdown 中使用内联 CSS，所以只能放弃了

def process_windhawk(image_list):
    url = WINDHAWK_CATALOG_URL

    # 1. 在获取前加载历史记录，用于计算日增量
    history = load_history()
    new_history = {}

    try:
        data = fetch_json(url)
    except Exception as e:
        # 保留你要求的错误提示格式
        # 注意：此处假设你全局定义了 REQUEST_TIMEOUT，若无则会抛出变量未定义异常
        print(f"获取 Windhawk 数据失败（超时视为失败）: {e}")
        return []

    my_mods = []
    # 遍历 mods 字典
    for mod_id, mod_info in data.get('mods', {}).items():
        if mod_info.get('metadata', {}).get('author') == WINDHAWK_AUTHOR:
            # 提取核心数值
            users = mod_info['details']['users']
            rating_score = mod_info['details'].get('rating', 0)

            # --- 计算日增量 (Delta) ---
            # 如果历史记录中没有该 ID，则增量记为 0
            prev_users = history.get(mod_id, users)
            daily_delta = users - prev_users
            # 存入本次的新数据
            new_history[mod_id] = users

            # --- 查找匹配图片 ---
            best_img_url = find_best_image(mod_id, image_list)

            # --- 构建完整字典，无任何字段省略 ---
            my_mods.append({
                'id': mod_id,
                'name': mod_info['metadata']['name'],
                'desc': mod_info['metadata']['description'],
                'version': mod_info['metadata']['version'],
                'users': users,
                'rating_text': format_rating(rating_score), # 转换 0-10 到 "X.X ★"
                'daily': daily_delta,                       # 日增量数值
                'url': f"https://windhawk.net/mods/{mod_id}",
                'img_url': best_img_url                      # 存入图片 URL
            })

    # 2. 将本次抓取到的用户总数保存到 history.json，供下次运行对比
    save_history(new_history)

    # 按用户量降序排序
    my_mods.sort(key=lambda x: x['users'], reverse=True)
    return my_mods

def process_greasyfork():
    url = GREASYFORK_USER_URL
    try:
        data = fetch_json(url)
    except Exception as e:
        print(f"获取 GreasyFork 数据失败，请检查用户 ID 是否正确: {e}")
        return []

    my_scripts = []
    # 【修改点 1】：改为遍历 data.get('scripts', [])
    for script in data.get('scripts', []):
        my_scripts.append({
            'name': script['name'],
            'desc': script['description'],
            'version': script['version'],
            'users': script['total_installs'],
            'url': script['url'],
            # 【修改点 2】：新增有效信息提取
            'daily': script['daily_installs'],
            'good_ratings': script['good_ratings']
        })

    my_scripts.sort(key=lambda x: x['users'], reverse=True)
    return my_scripts

def main():
    print("=== 开始生成 Markdown ===")

    # 0. 提前获取图片列表
    image_list = fetch_image_list()

    # 1. 处理 Windhawk 数据 (传入图片列表进行匹配)
    windhawk_items = process_windhawk(image_list)
    print(f"-> 找到 {len(windhawk_items)} 个 Windhawk 模块")

    # 2. 处理 GreasyFork 数据
    greasyfork_items = process_greasyfork()
    print(f"-> 找到 {len(greasyfork_items)} 个 GreasyFork 脚本")

    # 3. 拼接最终 Markdown 内容
    final_md = "## 🛠️ 我的开源项目\n\n"

    final_md += "### 🦅 Windhawk 模块 (Windhawk Mods)\n\n"
    final_md += generate_table(windhawk_items, platform="windhawk")

    final_md += "<br>\n\n" # 板块间距

    final_md += "### 🐵 油猴脚本 (GreasyFork Scripts)\n\n"
    final_md += generate_table(greasyfork_items, platform="greasyfork")

    # 4. 写入文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(final_md)

    print(f"\n✅ 成功！Markdown 代码已保存至 {OUTPUT_FILE}。")

if __name__ == "__main__":
    main()