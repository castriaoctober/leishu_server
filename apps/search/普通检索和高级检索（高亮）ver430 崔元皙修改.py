# 4.30崔元皙修改
import json
import re
import pymysql

# 4.30 已通过检查（检查人：崔元皙）
# 从数据库连接配置
def get_mysql_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='gczwbmfs',  # 请确保这是您的 MySQL 密码
        db='leishu_yongle',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# 4.30 已通过检查（检查人：崔元皙）
def normalize_keyword(keyword: str) -> str:
    keyword = keyword.replace("(", "").replace(")", "")  # 去除括号
    keyword = re.sub(r'(?i)(AND|OR|NOT)', r' \1 ', keyword)  # 在逻辑运算符两侧插入空格
    keyword = re.sub(r'\s+', ' ', keyword)  # 删除多余空格
    return keyword.strip()

# 4.30 已通过检查（检查人：崔元皙）
# 关键词解析函数
def parse_keyword_to_match(keyword: str, column: str, search_option: str = "精确") -> str:
    keyword = normalize_keyword(keyword)  # 标准化关键词
    or_groups = re.split(r'\s+OR\s+', keyword, flags=re.IGNORECASE)  # 按 OR 分组
    match_clauses = []  # 存放每组生成的匹配语句

    for group in or_groups:
        tokens = group.split()  # 分词
        boolean_terms = []  # 存放布尔关键词
        prev = ""  # 跟踪前一个逻辑运算符

        for token in tokens:
            upper = token.upper()
            if upper == "AND":
                prev = "AND"  # 标记为 AND（此实现中实际未用）
            elif upper == "NOT":
                prev = "NOT"  # 标记为 NOT，用于下一个词前加负号
            else:
                if prev == "NOT":
                    boolean_terms.append(f"-{token}")  # NOT 表示必须不包含
                else:
                    boolean_terms.append(f"+{token}")  # 默认表示必须包含
                prev = ""  # 重置逻辑标记

        match_clause = f"MATCH({column}) AGAINST('{ ' '.join(boolean_terms) }' IN BOOLEAN MODE)"  # 构造 MATCH 查询

        if search_option == "模糊":
            match_clause = match_clause.replace("IN BOOLEAN MODE", "IN NATURAL LANGUAGE MODE")

        match_clauses.append(f"({match_clause})")  # 加括号保留逻辑顺序

    return f"({' OR '.join(match_clauses)})"  # 使用 OR 连接各组匹配语句并整体加括号

# 4.30 已通过检查（检查人：崔元皙）
# 构建SQL条件子句
def build_sql_from_conditions(conditions):
    def split_logic_blocks(conditions):
        blocks = []  # 存放 OR 分组块
        current_block = []  # 当前分组

        for cond in conditions:
            if cond['logic'].upper() == "OR" and current_block:
                blocks.append(current_block)  # 遇到 OR，结束当前分组
                current_block = [cond]  # 开始新分组
            else:
                current_block.append(cond)  # 否则加入当前分组

        if current_block:
            blocks.append(current_block)  # 加入最后一组

        return blocks

    blocks = split_logic_blocks(conditions)  # 分组条件
    block_clauses = []  # 存放每组的 SQL 子句

    for block in blocks:
        sub_clauses = []  # 存放当前分组的每个条件的子句
        for cond in block:
            col = cond["column"]  # 获取列名
            keyword = cond["keyword"]  # 获取关键词
            search_option = cond.get("search_option", "精确")  # 默认精确搜索
            if col == "doc_title":
                clause = f"MATCH(d.{col}) AGAINST('{keyword}' IN BOOLEAN MODE)"  # 标题全文搜索
                if search_option == '模糊':
                    clause.replace("IN BOOLEAN MODE", "IN NATURAL LANGUAGE MODE")
            elif col == "full_text":
                clause = parse_keyword_to_match(keyword, "f.full_text",search_option)  # 正文全文搜索
            elif col == "author_name":
                clause = parse_keyword_to_match(keyword, "a.author_name",search_option)  # 作者名搜索
            elif col == "author_org":
                clause = parse_keyword_to_match(keyword, "a.author_org",search_option)  # 作者机构搜索
            elif col == "title_name":
                clause = parse_keyword_to_match(keyword, "t.title_name",search_option)  # 期刊名搜索
            else:
                continue  # 忽略未知列

            sub_clauses.append(f"({clause})")  # 用括号包裹每个子句

        block_clauses.append(" AND ".join(sub_clauses))  # 同一分组内使用 AND 连接

    return " OR ".join(f"({block})" for block in block_clauses)  # 各分组之间使用 OR 连接并加括号

# 4.30 已通过检查（检查人：崔元皙）
# 构建完整SQL查询
def advanced_search_build_sql(conditions):
    from_clause = "FROM documents d"  # 主表
    joins = []  # 存放需要的 JOIN 语句
    select_fields = ["d.*"]  # 查询字段初始包含主表所有字段
    used_columns = {cond["column"] for cond in conditions}  # 获取用到的所有列

    if {"author_name", "author_org"} & used_columns:
        joins.append("inner join document_author_links dal ON dal.doc_id = d.doc_id")  # 连接作者关联表
        joins.append("inner join authors a ON a.author_id = dal.author_id")  # 连接作者表
        select_fields.append("a.*")  # 包含作者信息
        select_fields.append("dal.*")  # 包含关联信息

    if "title_name" in used_columns:
        joins.append("inner join titles t ON t.doc_id = d.doc_id")  # 连接期刊信息表
        select_fields.append("t.*")  # 包含期刊信息字段

    if "full_text" in used_columns:
        joins.append("inner join full_text_1 f ON f.doc_id = d.doc_id")  # 连接全文表
        select_fields.append("f.*")  # 包含全文字段

    where_clause = build_sql_from_conditions(conditions)  # 构建 WHERE 子句

    # === 检查 title_name 和 full_text 是否在同一个 AND 逻辑块中 ===
    def get_and_clusters(conditions):
        clusters = []  # 存放 AND 逻辑块集合
        current_cluster = []  # 当前逻辑块

        for i, cond in enumerate(conditions):
            if i == 0 or cond["logic"].upper().strip() == "AND":
                current_cluster.append(cond["column"])  # 连续 AND 加入同一块
            else:
                if current_cluster:
                    clusters.append(set(current_cluster))  # 新块开始前保存旧块
                current_cluster = [cond["column"]]  # 新块
        if current_cluster:
            clusters.append(set(current_cluster))  # 添加最后一块
        return clusters

    clusters = get_and_clusters(conditions)
    needs_title_id_match = any({"full_text", "title_name"}.issubset(cluster) for cluster in clusters)  # 判断是否需额外关联 title_id

    if needs_title_id_match:
        extra_condition = "f.title_id = t.title_id"  # 添加额外条件
        if where_clause:
            where_clause += f" AND {extra_condition}"  # 拼接到已有 WHERE 子句
        else:
            where_clause = extra_condition  # 单独作为 WHERE 子句

    # === 拼接最终 SQL 查询语句 ===
    sql = f"SELECT DISTINCT {', '.join(select_fields)}\n{from_clause}"
    if joins:
        sql += "\n" + "\n".join(joins)
    if where_clause:
        sql += "\nWHERE " + where_clause
    sql += "\nLIMIT 100;"  # 限制返回行数

    return sql


# 4.30 已通过检查（检查人：崔元皙）
def all_fields_search(original_conditions: list, conn) -> list:
    """
    负责处理 all_fields 搜索逻辑：
    - 对元数据字段（4个）使用 OR 搜索
    - 对 full_text 单独进行搜索
    - 分别限制为 LIMIT 5 并执行高级搜索
    - enrich 后合并结果
    """

    # 1️⃣ 提取用户 keyword 和搜索选项
    keyword = original_conditions[0]["keyword"].strip()
    search_option = original_conditions[0].get("search_option", "精确")

    # 2️⃣ 构造元字段搜索条件
    meta_conditions = [
        {"column": "doc_title", "keyword": keyword, "logic": "", "search_option": search_option},
        {"column": "author_name", "keyword": keyword, "logic": "OR", "search_option": search_option},
        {"column": "author_org", "keyword": keyword, "logic": "OR", "search_option": search_option},
        {"column": "title_name", "keyword": keyword, "logic": "OR", "search_option": search_option},
    ]

    # 3️⃣ 构造 full_text 搜索条件
    fulltext_condition = [{
        "column": "full_text",
        "keyword": keyword,
        "logic": "",
        "search_option": search_option
    }]

    # 4️⃣ 生成 SQL 查询语句
    sql_meta = advanced_search_build_sql(meta_conditions).replace("LIMIT 100", "LIMIT 5")  # 限制行数为 5
    if search_option == "模糊":
        sql_meta = sql_meta.replace("IN BOOLEAN MODE", "IN NATURAL LANGUAGE MODE")  # 模糊搜索切换模式

    sql_full = advanced_search_build_sql(fulltext_condition).replace("LIMIT 100", "LIMIT 5")
    if search_option == "模糊":
        sql_full = sql_full.replace("IN BOOLEAN MODE", "IN NATURAL LANGUAGE MODE")
    # 5️⃣ 执行查询并进行字段补全（enrich）
    cursor = conn.cursor()
    cursor.execute(sql_meta)
    result_meta = cursor.fetchall()
    enriched_meta = enrich_results_with_missing_info(conn, result_meta)

    cursor.execute(sql_full)
    result_full = cursor.fetchall()
    enriched_full = enrich_results_with_missing_info(conn, result_full)

    cursor.close()

    # 6️⃣ 合并两部分结果并返回
    return enriched_meta + enriched_full

# 获取额外字段
# 4.30 已通过检查（检查人：崔元皙）
def fetch_extra_fields(conn, doc_id, title_id=None):
    """
    根据 doc_id（和可选 title_id）补全代表字段：
    - title_name：最多两个，自动加“等”
    - author_name / author_org：最多两个，自动加“等”
    - full_text：从 title_id 开始查找最近的 full_text，不行则回退到 doc_id
    """
    enriched = {}

    def get_nearest_text_by_title_id(cursor, title_id):
        cursor.execute("""
            SELECT full_text 
            FROM full_text_1 
            WHERE title_id = %s 
            ORDER BY full_text_order ASC 
            LIMIT 1
        """, (title_id,))
        row = cursor.fetchone()
        if row and row["full_text"]:
            return row["full_text"][:100] + "···"  # 截取前100字作为预览文本

        # 递归向下查找子标题的全文
        cursor.execute("SELECT title_id FROM titles WHERE parent_id = %s", (title_id,))
        children = cursor.fetchall()
        for child in children:
            text = get_nearest_text_by_title_id(cursor, child["title_id"])
            if text:
                return text
        return None  # 没有找到可用的全文

    with conn.cursor() as cursor:
        # 获取标题（title_name）
        cursor.execute("SELECT title_name FROM titles WHERE doc_id = %s LIMIT 2", (doc_id,))
        rows = cursor.fetchall()
        if rows:
            title = rows[0]["title_name"]
            if len(rows) > 1:
                title += " 等"  # 超过一个标题则添加“等”
            enriched["title_name"] = title
        else:
            enriched["title_name"] = None

        # 获取作者信息（最多两个）
        cursor.execute("""
            SELECT a.author_name, a.author_org
            FROM authors a
            JOIN document_author_links dal ON dal.author_id = a.author_id
            WHERE dal.doc_id = %s
            LIMIT 2
        """, (doc_id,))
        rows = cursor.fetchall()
        if rows:
            name = rows[0]["author_name"]
            if len(rows) > 1:
                name += " 等"  # 超过一个作者则添加“等”
            enriched["author_name"] = name
            enriched["author_org"] = rows[0]["author_org"]
        else:
            enriched["author_name"] = None
            enriched["author_org"] = None

        # 获取全文（full_text）：优先根据 title_id 查找，若无则 fallback 到 doc_id
        if title_id:
            text = get_nearest_text_by_title_id(cursor, title_id)
            if text:
                enriched["full_text"] = text
            else:
                cursor.execute("""
                    SELECT full_text 
                    FROM full_text_1 
                    WHERE doc_id = %s 
                    ORDER BY full_text_order ASC 
                    LIMIT 1
                """, (doc_id,))
                row = cursor.fetchone()
                enriched["full_text"] = row["full_text"][:100] + "···" if row and row["full_text"] else None
        else:
            cursor.execute("""
                SELECT full_text 
                FROM full_text_1 
                WHERE doc_id = %s 
                ORDER BY full_text_order ASC 
                LIMIT 1
            """, (doc_id,))
            row = cursor.fetchone()
            enriched["full_text"] = row["full_text"][:100] + "···" if row and row["full_text"] else None

    return enriched

# 4.30 已通过检查（检查人：崔元皙）
# 根据缺失字段与 title_id 判断，智能补全结果中的 title/full_text/作者字段
def enrich_results_with_missing_info(conn, results):
    """
    根据 doc_id 和 title_id，补全缺失字段（title_name, author_name, author_org, full_text）。
    针对不同情况智能选择补全逻辑：
    1. title 和 full_text 都使用 → 使用 title_id 精确获取 full_text
    2. 只有 title 使用 → 用 title_id 找到相关 full_text
    3. 只有 full_text 使用 → 用 title_id 找到相关 title_name
    4. 都没有 → 用 doc_id 获取默认 full_text 和 title_name
    """
    must_fields = ["title_name", "author_name", "author_org", "full_text"]  # 所有需要补全的字段
    enriched_results = []  # 存储最终结果列表

    for row in results:
        doc_id = row["doc_id"]  # 获取文档 ID
        title_id = row.get("title_id")  # 获取可选的 title_id
        missing_fields = [field for field in must_fields if field not in row]  # 检查缺失字段

        if missing_fields:
            extra_data = fetch_extra_fields(conn, doc_id, title_id)  # 获取补全数据
            for key in missing_fields:
                row[key] = extra_data.get(key)  # 逐项填充缺失字段

        enriched_results.append(row)  # 加入最终结果列表

    return enriched_results  # 返回补全后的所有结果

# 4.30 已通过检查（检查人：崔元皙）
# 4月24日更新日志：删除把所有boolean改为natural的代码
# 构建最终 SQL 或调用 all_fields 搜索（根据字段判断）
def build_final_sql(search_conditions, conn=None):
    if any(cond["column"] == "all_fields" for cond in search_conditions):
        if conn is None:
            raise ValueError("MySQL connection required for all_fields_search.")  # all_fields 搜索需要数据库连接
        return all_fields_search(search_conditions, conn)  # 返回全字段搜索结果
    else:
        sql = advanced_search_build_sql(search_conditions)  # 构建标准 SQL 查询
        return sql
    
# 4.30 已通过检查（检查人：崔元皙）
# 高亮预处理函数
def extract_chinese_chars_per_field(conditions):
    result = {}
    for cond in conditions:
        col = cond.get("column")
        keyword = cond.get("keyword", "")
        chars = re.findall(r'[\u4e00-\u9fff]', keyword)
        if col and chars:
            if col not in result:
                result[col] = set()
            result[col].update(chars)
    return {k: list(v) for k, v in result.items()}

# 4.30 已通过检查（检查人：崔元皙）
# 高亮函数
def highlight_text(text, chars):
    if not text or not chars:
        return text
    try:
        for ch in chars:
            pattern = re.compile(f'({re.escape(ch)})', re.IGNORECASE)
            text = pattern.sub(r"\033[1;31m\1\033[0m", text)
        return text
    except Exception as e:
        print(f"高亮处理出错: {str(e)}")
        return text


# 4.30 已通过检查（检查人：崔元皙）
# 执行搜索并打印结果
def perform_search(conditions):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    
    try:
        sql_or_results = build_final_sql(search_conditions, conn) # 前端只需调用它即可
        print(sql_or_results)
        if isinstance(sql_or_results, str):
            cursor.execute(sql_or_results)
            results = cursor.fetchall()
            final_results = enrich_results_with_missing_info(conn, results)
        else:
            final_results = sql_or_results  # already enriched from all_fields_search
        
         # 为结果添加高亮
        if any(cond.get("column") == "all_fields" for cond in conditions):
            all_text = ''.join(cond.get("keyword", "") for cond in conditions)
            highlight_chars = list(set(re.findall(r'[\u4e00-\u9fff]', all_text)))
            highlight_dict = {field: highlight_chars for field in ["doc_title", "author_name", "author_org", "title_name", "full_text"]}
        else:
            highlight_dict = extract_chinese_chars_per_field(conditions)

        highlighted_results = []
        for result in final_results:
            highlighted_result = result.copy()
            for field in ["doc_title", "author_name", "author_org", "title_name", "full_text"]:
                if result.get(field) and field in highlight_dict:
                    highlighted_result[field] = highlight_text(result[field], highlight_dict[field])
            highlighted_results.append(highlighted_result)


        
        # 打印结果
        print(f"搜索结果 ({len(highlighted_results)} 条):")
        for i, result in enumerate(highlighted_results, 1):
            print(f"\n结果 {i}:")
            print(f"  标题: {result.get('doc_title', '无')}")
            print(f"  作者: {result.get('author_name', '无')}")
            print(f"  作者机构: {result.get('author_org', '无')}")
            print(f"  期刊名: {result.get('title_name', '无')}")
            print(f"  内容摘要: {result.get('full_text', '无')}")
    
    finally:
        conn.close()

# 4.30 已通过检查（检查人：崔元皙）
# 主程序
if __name__ == "__main__":
    # 定义搜索条件
    search_conditions = [
       # {"column": "author_name", "keyword": "解", "logic": "", "search_option": "精确"},
       # {"column": "author_org", "keyword": "明朝翰林院", "logic": "AND", "search_option": "精确"},
        {"column": "full_text", "keyword": "即自是山林not利欲 ", "logic": "AND", "search_option": "精确"}
    ]

        
    # 执行搜索
    perform_search(search_conditions)