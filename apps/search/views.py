import json
import re
import pymysql
from django.http import JsonResponse
from django.db import connection
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from collections import defaultdict
from utils.database import connect_db

def get_mysql_connection():
    return connect_db(cursorclass=pymysql.cursors.DictCursor)  # 使用字典游标返回结果

def build_final_sql(search_conditions, conn=None):
    if any(cond["column"] == "all_fields" for cond in search_conditions):
        if conn is None:
            raise ValueError("MySQL connection required for all_fields_search.")  # all_fields 搜索需要数据库连接
        return all_fields_search(search_conditions, conn)  # 返回全字段搜索结果
    else:
        sql = advanced_search_build_sql(search_conditions)  # 构建标准 SQL 查询
        return sql

def enrich_results_with_missing_info(conn, results):
    """
    根据 doc_id 和 title_id，补全缺失字段（title_name, author_name, author_org, full_text）。
    针对不同情况智能选择补全逻辑：
    1. title 和 full_text 都使用 → 使用 title_id 精确获取 full_text
    2. 只有 title 使用 → 用 title_id 找到相关 full_text
    3. 只有 full_text 使用 → 用 title_id 找到相关 title_name
    4. 都没有 → 用 doc_id 获取默认 full_text 和 title_name
    """
    must_fields = ["title_name", "author_name", "author_org", "full_text", "page_id"]  # 所有需要补全的字段
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

def fetch_extra_fields(conn, doc_id, title_id=None):
    """
    根据 doc_id（和可选 title_id）补全代表字段：
    - title_name：最多两个，自动加"等"
    - author_name / author_org：最多两个，自动加"等"
    - full_text：从 title_id 开始查找最近的 full_text，不行则回退到 doc_id
    - page_id：通过page_number和doc_id获取对应的page_id
    """
    enriched = {}

    def get_nearest_text_by_title_id(cursor, title_id):
        cursor.execute("""
            SELECT full_text, page_number, page_type
            FROM full_text_1
            WHERE title_id = %s
            ORDER BY full_text_order ASC
            LIMIT 1
        """, (title_id,))
        row = cursor.fetchone()
        if row and row["full_text"]:
            # 获取page_id
            page_number = row.get("page_number")
            page_type = row.get("page_type")
            if page_number:
                cursor.execute("""
                    SELECT page_id
                    FROM pages
                    WHERE doc_id = %s AND page_number = %s AND page_type = %s
                    LIMIT 1
                """, (doc_id, page_number, page_type))
                page_row = cursor.fetchone()
                enriched["page_id"] = page_row["page_id"] if page_row else None

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
                title += " 等"  # 超过一个标题则添加"等"
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
                name += " 等"  # 超过一个作者则添加"等"
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
                    SELECT full_text, page_number, page_type
                    FROM full_text_1
                    WHERE doc_id = %s
                    ORDER BY full_text_order ASC
                    LIMIT 1
                """, (doc_id,))
                row = cursor.fetchone()
                enriched["full_text"] = row["full_text"][:100] + "···" if row and row["full_text"] else None

                # 获取page_id
                if row and row.get("page_number"):
                    cursor.execute("""
                        SELECT page_id
                        FROM pages
                        WHERE doc_id = %s AND page_number = %s AND page_type = %s
                        LIMIT 1
                    """, (doc_id, row["page_number"], row["page_type"]))
                    page_row = cursor.fetchone()
                    enriched["page_id"] = page_row["page_id"] if page_row else None
        else:
            cursor.execute("""
                SELECT full_text, page_number, page_type
                FROM full_text_1
                WHERE doc_id = %s
                ORDER BY full_text_order ASC
                LIMIT 1
            """, (doc_id,))
            row = cursor.fetchone()
            enriched["full_text"] = row["full_text"][:100] + "···" if row and row["full_text"] else None

            # 获取page_id
            if row and row.get("page_number"):
                cursor.execute("""
                    SELECT page_id
                    FROM pages
                    WHERE doc_id = %s AND page_number = %s AND page_type = %s
                    LIMIT 1
                """, (doc_id, row["page_number"], row["page_type"]))
                page_row = cursor.fetchone()
                enriched["page_id"] = page_row["page_id"] if page_row else None

    return enriched

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

# def highlight_text(text, chars):
#     if not text or not chars:
#         return text
#     try:
#         for ch in chars:
#             pattern = re.compile(f'({re.escape(ch)})', re.IGNORECASE)
#             text = pattern.sub(r'<span class="highlight">\1</span>', text)
#         return text
#     except Exception as e:
#         print(f"高亮处理出错: {str(e)}")
#         return text

# 修改后的高亮函数
def highlight_text(text, chars):
    if not text or not chars:
        return text
    try:
        # 将字符列表转换为正则表达式模式，匹配连续的字符
        pattern_str = ''.join(re.escape(ch) for ch in chars)
        pattern = re.compile(f'([{pattern_str}]+)', re.IGNORECASE)
        def repl(match):
            return f'<span class="highlight">{match.group(1)}</span>'
        return pattern.sub(repl, text)
    except Exception as e:
        print(f"高亮处理出错: {str(e)}")
        return text


def perform_search(conditions):
    conn = get_mysql_connection()
    cursor = conn.cursor()

    try:
        sql_or_results = build_final_sql(conditions, conn) # 前端只需调用它即可
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

        return {
            'total': len(highlighted_results),
            'results': highlighted_results
        }

    finally:
        conn.close()

def all_fields_search(original_conditions: list, conn) -> list:
    """
    负责处理 all_fields 搜索逻辑：
    - 对元数据字段（4个）使用 OR 搜索
    - 对 full_text 单独进行搜索
    - 分别限制为 LIMIT 5 并执行高级搜索
    - enrich 后合并结果
    """

    # 1️⃣ 提取用户 keyword 和搜索选项以及过滤条件
    main_condition = next((cond for cond in original_conditions if cond["column"] == "all_fields"), None)
    if not main_condition:
        raise ValueError("all_fields搜索条件缺失")

    keyword = main_condition["keyword"].strip()
    search_option = main_condition.get("search_option", "精确")

    # 提取过滤条件
    filter_conditions = [cond for cond in original_conditions if cond["column"] != "all_fields"]
    print(f"提取的过滤条件: {filter_conditions}")

    # 2️⃣ 构造元字段搜索条件
    meta_conditions = [
        {"column": "doc_title", "keyword": keyword, "logic": "", "search_option": search_option},
        {"column": "author_name", "keyword": keyword, "logic": "OR", "search_option": search_option},
        {"column": "author_org", "keyword": keyword, "logic": "OR", "search_option": search_option},
        {"column": "title_name", "keyword": keyword, "logic": "OR", "search_option": search_option},
    ]

    # 加入过滤条件
    for cond in filter_conditions:
        meta_conditions.append({"column": cond["column"], "keyword": cond["keyword"], "logic": "AND", "search_option": "精确"})

    # 3️⃣ 构造 full_text 搜索条件
    fulltext_condition = [{
        "column": "full_text",
        "keyword": keyword,
        "logic": "",
        "search_option": search_option
    }]

    # 加入过滤条件
    for cond in filter_conditions:
        fulltext_condition.append({"column": cond["column"], "keyword": cond["keyword"], "logic": "AND", "search_option": "精确"})

    # 4️⃣ 生成 SQL 查询语句
    sql_meta = advanced_search_build_sql(meta_conditions).replace("LIMIT 100", "LIMIT 5")  # 限制行数为 5
    if search_option == "模糊":
        sql_meta = sql_meta.replace("IN BOOLEAN MODE", "IN NATURAL LANGUAGE MODE")  # 模糊搜索切换模式

    sql_full = advanced_search_build_sql(fulltext_condition).replace("LIMIT 100", "LIMIT 5")
    if search_option == "模糊":
        sql_full = sql_full.replace("IN BOOLEAN MODE", "IN NATURAL LANGUAGE MODE")

    # 输出调试信息，显示SQL语句
    print(f"元数据查询SQL: {sql_meta}")
    print(f"全文查询SQL: {sql_full}")

    # 5️⃣ 执行查询并进行字段补全（enrich）
    cursor = conn.cursor()
    cursor.execute(sql_meta)
    result_meta = cursor.fetchall()
    print(f"元数据查询结果数: {len(result_meta)}")
    enriched_meta = enrich_results_with_missing_info(conn, result_meta)

    cursor.execute(sql_full)
    result_full = cursor.fetchall()
    print(f"全文查询结果数: {len(result_full)}")
    enriched_full = enrich_results_with_missing_info(conn, result_full)

    cursor.close()

    # 6️⃣ 合并两部分结果并返回
    all_results = enriched_meta + enriched_full
    print(f"合并后结果数: {len(all_results)}")
    return all_results

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

            # 处理过滤条件
            if col == "category_type":
                clause = f"d.category_type = '{keyword}'"
            elif col == "doc_specific_category":
                clause = f"d.doc_specific_category = '{keyword}'"
            elif col == "doc_style":
                clause = f"d.doc_style = '{keyword}'"
            # 处理搜索条件
            elif col == "doc_title":
                clause = f"MATCH(d.{col}) AGAINST('{keyword}' IN BOOLEAN MODE)"  # 标题全文搜索
                if search_option == '模糊':
                    clause = clause.replace("IN BOOLEAN MODE", "IN NATURAL LANGUAGE MODE")
            elif col == "full_text":
                clause = parse_keyword_to_match(keyword, "f.full_text", search_option)  # 正文全文搜索
            elif col == "author_name":
                clause = parse_keyword_to_match(keyword, "a.author_name", search_option)  # 作者名搜索
            elif col == "author_org":
                clause = parse_keyword_to_match(keyword, "a.author_org", search_option)  # 作者机构搜索
            elif col == "title_name":
                clause = parse_keyword_to_match(keyword, "t.title_name", search_option)  # 期刊名搜索
            else:
                continue  # 忽略未知列

            sub_clauses.append(f"({clause})")  # 用括号包裹每个子句

        if sub_clauses:  # 只有当有子句时才添加到block_clauses
            block_clauses.append(" AND ".join(sub_clauses))  # 同一分组内使用 AND 连接

    if not block_clauses:  # 如果没有任何条件
        return "1=1"  # 返回永真条件

    return " OR ".join(f"({block})" for block in block_clauses)  # 各分组之间使用 OR 连接并加括号

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

def normalize_keyword(keyword: str) -> str:
    keyword = keyword.replace("。", " ")  #5月4日崔元皙添加
    keyword = keyword.replace("(", "").replace(")", "")  # 去除括号
    keyword = re.sub(r'(?i)(AND|OR|NOT)', r' \1 ', keyword)  # 在逻辑运算符两侧插入空格
    keyword = re.sub(r'\s+', ' ', keyword)  # 删除多余空格
    return keyword.strip()

# 基本检索视图
@csrf_exempt
@require_http_methods(['POST'])
def basic_search(request):
    try:
        data = json.loads(request.body)  # 解析请求体
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    query = data.get('query', '')
    search_field = data.get('search_field', 'all_fields')
    filters = data.get('filters', {})
    search_option = data.get('search_option', '精确')  # 新增搜索选项，默认为精确

    # 打印输入的查询信息
    print("接收到的查询信息:")
    print(f"查询字符串: {query}")
    print(f"搜索字段: {search_field}")
    print(f"搜索选项: {search_option}")
    print(f"过滤条件: {filters}")

    # 构建搜索条件
    conditions = []

    if search_field == 'all_fields':
        conditions = [{"column": "all_fields", "keyword": query, "logic": "", "search_option": search_option}]
        # 处理过滤条件
        if filters:
            if filters.get('category_type'):
                conditions.append({"column": "category_type", "keyword": filters['category_type'], "logic": "AND"})
            if filters.get('specific_category'):
                conditions.append({"column": "doc_specific_category", "keyword": filters['specific_category'], "logic": "AND"})
            if filters.get('document_type'):
                conditions.append({"column": "doc_style", "keyword": filters['document_type'], "logic": "AND"})

        print(f"构建搜索条件: {conditions}")

        # 使用全字段搜索逻辑
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='Leishu2025!',
            db='leishu_yongle',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        results = all_fields_search(conditions, conn)
        conn.close()
    else:
        # 为单一字段构建查询条件
        if search_field == 'literature':
            conditions.append({"column": "doc_title", "keyword": query, "logic": "", "search_option": search_option})
        elif search_field == 'author':
            conditions.append({"column": "author_name", "keyword": query, "logic": "", "search_option": search_option})
        elif search_field == 'title':
            conditions.append({"column": "title_name", "keyword": query, "logic": "", "search_option": search_option})
        elif search_field == 'full_text':
            conditions.append({"column": "full_text", "keyword": query, "logic": "", "search_option": search_option})

        # 处理过滤条件
        if filters:
            if filters.get('category_type'):
                conditions.append({"column": "category_type", "keyword": filters['category_type'], "logic": "AND"})
            if filters.get('specific_category'):
                conditions.append({"column": "doc_specific_category", "keyword": filters['specific_category'], "logic": "AND"})
            if filters.get('document_type'):
                conditions.append({"column": "doc_style", "keyword": filters['document_type'], "logic": "AND"})

    # 使用统一的搜索处理函数
    search_results = perform_search(conditions)

    # 打印一些调试信息
    print(f"搜索结果总数: {search_results.get('total', 0)}")

    # 输出"返回给前端的信息"
    print("返回给前端的信息", search_results)

    return JsonResponse(search_results)


# 高级检索视图
@csrf_exempt
@require_http_methods(['POST'])
def advanced_search(request):
    try:
        data = json.loads(request.body)  # 解析请求体
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    advancedQueries = data.get('queries', [])  # 获取高级检索的查询条件
    filters = data.get('filters', {})

    # 打印输入的查询信息
    print("接收到的高级检索信息:")
    print(f"查询条件: {advancedQueries}")
    print(f"过滤条件: {filters}")

    # 构建搜索条件
    conditions = []
    for i, query in enumerate(advancedQueries):
        field = query['field']
        logic = query.get('operator', '')
        search_value = query['value']

        if i > 0 and logic:  # 确保第一个条件不添加逻辑符
            logic = logic.upper()  # 转为大写以符合处理逻辑

        # 字段映射
        column_map = {
            'literature': 'doc_title',
            'author': 'author_name',
            'title': 'title_name',
            'full_text': 'full_text'
        }

        column = column_map.get(field, field)

        conditions.append({
            "column": column,
            "keyword": search_value,
            "logic": logic,
            "search_option": query.get('search_option', '精确')  # 获取搜索选项，默认精确
        })

    # 处理过滤条件
    if filters:
        if filters.get('category_type'):
            conditions.append({"column": "category_type", "keyword": filters['category_type'], "logic": "AND"})
        if filters.get('specific_category'):
            conditions.append({"column": "doc_specific_category", "keyword": filters['specific_category'], "logic": "AND"})
        if filters.get('document_type'):
            conditions.append({"column": "doc_style", "keyword": filters['document_type'], "logic": "AND"})

     # 使用统一的搜索处理函数
    search_results = perform_search(conditions)

    # 打印一些调试信息
    print(f"搜索结果总数: {search_results.get('total', 0)}")

    # 输出"返回给前端的信息"
    print("返回给前端的信息", search_results)

    return JsonResponse(search_results)

# 其他视图函数（保留原有的其他视图函数）
def search(request):
    return render(request, 'search/search.html')

def search_results(request):
    return render(request, 'search/search_results.html')

def advanced_search_page(request):
    return render(request, 'search/advanced_search.html')

def screen(request):  # 筛选搜索结果
    fliter = request.POST.get('fliter', '')  # 过滤条件 checkbox
    sort_keys = request.POST.get('sort_keys', '')  # 排序条件

    return HttpResponse('fliter: %s, sort_keys: %s' % (fliter, sort_keys))

@csrf_exempt
@require_http_methods(['POST'])
def similar_search_milvus(request):
    """异文检索-milvus：使用向量数据库进行相似文本检索"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式'}, status=400)

    query_text = data.get('query', '')
    filters = data.get('filters', {})  # 获取过滤条件

    # 打印输入的查询信息和过滤条件
    print("接收到的异文检索信息:")
    print(f"查询文本: {query_text}")
    print(f"过滤条件: {filters}")

    if not query_text:
        return JsonResponse({'error': '请输入检索文本'}, status=400)

    # 显示Python环境和库信息
    import sys
    import os
    try:
        import pip
        installed_packages = sorted(["%s==%s" % (i.key, i.version) for i in pip.get_installed_distributions()])
    except:
        try:
            import pkg_resources
            installed_packages = sorted(["%s==%s" % (i.key, i.version) for i in pkg_resources.working_set])
        except:
            installed_packages = ["无法获取已安装的包信息"]

    python_info = {
        "python_version": sys.version,
        "python_path": sys.executable,
        "sys_path": sys.path,
        "current_dir": os.getcwd(),
        "env_vars": {k: v for k, v in os.environ.items() if 'PATH' in k or 'PYTHON' in k}
    }

    # 导入可选依赖，如果不存在则使用模拟结果
    try:
        import numpy as np
    except ImportError as e:
        return JsonResponse({
            'total': 1,
            'query': query_text,
            'results': [{
                'document_title': "依赖错误",
                'title_name': "缺少依赖库",
                'sentence': f"服务器未安装numpy库，请联系管理员安装依赖：pip install numpy pymilvus sentence-transformers\n错误详情: {str(e)}\n环境信息: Python {sys.version} 位于 {sys.executable}",
                'similarity': 0.0,
                'text_type': "错误"
            }]
        })

    try:
        from pymilvus import connections, Collection
    except ImportError as e:
        return JsonResponse({
            'total': 1,
            'query': query_text,
            'results': [{
                'document_title': "依赖错误",
                'title_name': "缺少依赖库",
                'sentence': f"服务器未安装pymilvus库，请联系管理员安装依赖：pip install pymilvus\n错误详情: {str(e)}",
                'similarity': 0.0,
                'text_type': "错误"
            }]
        })

    # 加载模型
    try:
        try:
            from sentence_transformers import models, SentenceTransformer

            # 修改为本地模型路径,请替换你的存放地址
            local_model_path = "C://Users//14298//Desktop//bert-ancient-chinese"
            # 直接加载本地模型
            word_embedding_model = models.Transformer(local_model_path)
            pooling_model = models.Pooling(
                word_embedding_model.get_word_embedding_dimension(),
                pooling_mode_mean_tokens=True
            )
            model = SentenceTransformer(modules=[word_embedding_model, pooling_model])
        except ImportError as e:
            error_msg = str(e)
            # 检查是否是HTTPError导入问题
            if "HTTPError" in error_msg and "requests" in error_msg:
                # 尝试修复requests问题
                import subprocess
                subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "requests"], capture_output=True)
                # 再次尝试导入
                from sentence_transformers import models, SentenceTransformer
                model_name = "Jihuai/bert-ancient-chinese"
                word_embedding_model = models.Transformer(model_name)
                pooling_model = models.Pooling(
                    word_embedding_model.get_word_embedding_dimension(),
                    pooling_mode_mean_tokens=True
                )
                model = SentenceTransformer(modules=[word_embedding_model, pooling_model])
            else:
                raise
    except Exception as e:
        return JsonResponse({
            'total': 1,
            'query': query_text,
            'results': [{
                'document_title': "模型加载错误",
                'title_name': "模型初始化失败",
                'sentence': f"无法加载模型: {str(e)}\n\n这可能是由于网络问题无法从HuggingFace下载模型，或者本地模型缓存损坏。",
                'similarity': 0.0,
                'text_type': "错误"
            }]
        })

    # 数据库配置
    DB_CONFIG = {
        "host": "localhost",
        "user": "root",
        "password": "Leishu2025!",
        "database": "leishu_yongle",
        "charset": "utf8mb4"
    }

    MILVUS_CONFIG = {
        "host": "localhost",
        "port": "19530"
    }

    # MySQL连接
    try:
        import pymysql
        db_connection = pymysql.connect(**DB_CONFIG)
        cursor = db_connection.cursor()
    except Exception as e:
        return JsonResponse({
            'total': 1,
            'query': query_text,
            'results': [{
                'document_title': "数据库连接错误",
                'title_name': "MySQL连接失败",
                'sentence': f"无法连接到MySQL数据库: {str(e)}",
                'similarity': 0.0,
                'text_type': "错误"
            }]
        })

    # Milvus连接
    try:
        connections.connect("default", **MILVUS_CONFIG)
    except Exception as e:
        # 关闭MySQL连接
        try:
            db_connection.close()
        except:
            pass

        return JsonResponse({
            'total': 1,
            'query': query_text,
            'results': [{
                'document_title': "向量数据库连接错误",
                'title_name': "Milvus连接失败",
                'sentence': f"无法连接到Milvus向量数据库: {str(e)}，请确保Milvus服务已启动。",
                'similarity': 0.0,
                'text_type': "错误"
            }]
        })

    # 工具函数
    def normalize_vector(vector):
        norm = np.linalg.norm(vector)
        return (vector / norm).tolist() if norm != 0 else vector

    def count_sentences(text):
        return text.count("。") + text.count("，")

    def get_collection_by_sentence_count(sentence_count):
        collections_map = {
        0: "yongle_1",
        1: "yongle_2",
        2: "yongle_3",
        3: "yongle_4"
        }

        return collections_map.get(sentence_count)

    # 执行相似检索
    result_list = []

    # 5.4 崔元皙添加的函数
    def to_boolean_query(text):
        fragments = re.split(r"[。]", text)
        tokens = [frag.strip().replace("　", "") for frag in fragments if frag.strip()]
        return " ".join(f"+{token}" for token in tokens)

    boolean_user_input = to_boolean_query(query_text) # 5.4 崔元皙添加

    try:
        user_query_fulltext_id = get_fulltext_id_from_mysql(cursor, query_text)
        sentence_count = count_sentences(query_text)
        collection_name = get_collection_by_sentence_count(sentence_count)

        if collection_name is None:
            return JsonResponse({
                'total': 1,
                'query': query_text,
                'results': [{
                    'document_title': "不支持的查询",
                    'title_name': "句子数量错误",
                    'sentence': f"请按照正确格式输入句子，标点符号最多有三个",
                    'similarity': 0.0,
                    'text_type': "错误"
                }]
            })

        try:
            collection = Collection(collection_name)
            collection.load()
        except Exception as e:
            return JsonResponse({
                'total': 1,
                'query': query_text,
                'results': [{
                    'document_title': "集合加载错误",
                    'title_name': "Milvus集合不存在",
                    'sentence': f"无法加载集合 {collection_name}: {str(e)}",
                    'similarity': 0.0,
                    'text_type': "错误"
                }]
            })

        # 向量编码查询
        query_vector = model.encode([query_text], convert_to_numpy=True)[0]
        query_vector = normalize_vector(query_vector)

        # 向量搜索，增加搜索限制到更多的结果，确保有足够的候选
        search_params = {"metric_type": "COSINE", "params": {"ef": 100}}
        results = collection.search([query_vector], "embedding", search_params, limit=50)  # 增加到50个结果供筛选

        filtered_results = []

        # 收集所有结果并过滤掉重复的文本
        for result in results[0]:
            text_id = result.id
            distance = result.distance

            try:
                sentence_data = collection.query(
                    f"id == {text_id}", output_fields=["fulltext_id", "sentence"]
                )[0]

                # 过滤掉与原始查询相同的文本
                if user_query_fulltext_id is not None and sentence_data["fulltext_id"] == user_query_fulltext_id:
                    continue

                doc_title, title_name, text_type, page_id, doc_id = get_fulltext_info(cursor, sentence_data["fulltext_id"])

                # 应用过滤条件
                if filters and any(filters.get(f) for f in ['category_type', 'specific_category', 'document_type', 'compilation_time']):
                    # 获取文档的元数据信息用于过滤
                    document_info = get_document_metadata(cursor, doc_id)

                    # 检查是否符合过滤条件
                    if not matches_filters(document_info, filters):
                        print(f"文档 {doc_id} 不符合过滤条件，已跳过")
                        continue

                filtered_results.append({
                    "collection_name": collection_name,
                    "fulltext_id": sentence_data["fulltext_id"],
                    "sentence": sentence_data["sentence"],
                    "similarity": round(distance, 4),
                    "document_title": doc_title,
                    "title_name": title_name,
                    "text_type": text_type,
                    "page_id": page_id,
                    "doc_id": doc_id
                })
            except Exception as e:
                print(f"处理搜索结果时出错: {str(e)}")

        # 确保最多返回10条结果，按相似度排序
        result_list = sorted(filtered_results, key=lambda x: x["similarity"], reverse=True)[:10]
        print(f"过滤后的结果数量: {len(result_list)}")

        # 对结果进行高亮处理
        for result in result_list:
            if result.get("sentence"):
                # 提取中文字符用于高亮
                highlight_chars = list(set(re.findall(r'[\u4e00-\u9fff]', query_text)))
                result["sentence"] = highlight_text(result["sentence"], highlight_chars)

    except Exception as e:
        result_list.append({
            "collection_name": "error",
            "fulltext_id": 0,
            "sentence": f"检索过程中出现错误: {str(e)}",
            "similarity": 0.0,
            "document_title": "处理错误",
            "title_name": "处理错误",
            "text_type": "错误",
            "page_id": None,
            "doc_id": None
        })

    # 关闭连接
    try:
        connections.disconnect("default")
    except:
        pass
    try:
        db_connection.close()
    except:
        pass

    # 只有在真的没有任何结果时（搜索过程中出错），才返回无结果提示
    if not result_list:
        result_list.append({
            "collection_name": "empty",
            "fulltext_id": 0,
            "sentence": "没有找到相似的文本。请尝试输入不同的文本或减少句子数量。",
            "similarity": 0.0,
            "document_title": "无结果",
            "title_name": "无结果",
            "text_type": "信息",
            "page_id": None,
            "doc_id": None
        })

    return JsonResponse({
        'total': len(result_list),
        'query': query_text,
        'results': result_list
    })

def get_document_metadata(cursor, doc_id):
    """获取文档的元数据信息"""
    try:
        sql = """
            SELECT category_type, doc_specific_category, doc_style, compilation_time
            FROM documents
            WHERE doc_id = %s
        """
        cursor.execute(sql, (doc_id,))
        result = cursor.fetchone()
        return result or {}
    except Exception as e:
        print(f"获取文档元数据失败: {str(e)}")
        return {}

def matches_filters(document_info, filters):
    """检查文档是否符合过滤条件"""
    if not filters:
        return True  # 没有过滤条件，所有文档都匹配

    # 检查每个过滤条件
    if filters.get('category_type') and filters['category_type'] and str(document_info.get('category_type')) != filters['category_type']:
        return False

    if filters.get('specific_category') and filters['specific_category'] and document_info.get('doc_specific_category') != filters['specific_category']:
        return False

    if filters.get('document_type') and filters['document_type'] and document_info.get('doc_style') != filters['document_type']:
        return False

    if filters.get('compilation_time') and filters['compilation_time'] and document_info.get('compilation_time') and filters['compilation_time'] not in document_info['compilation_time']:
        return False

    return True  # 所有条件都匹配

def get_fulltext_info(cursor, fulltext_id):
    """获取全文的基本信息"""
    try:
        sql = "SELECT doc_id, title_id, text_type, page_number, page_type FROM full_text_1 WHERE full_text_id = %s"
        cursor.execute(sql, (fulltext_id,))
        fulltext_info = cursor.fetchone()
        if not fulltext_info:
            return "未知文献", "未知标题", "未知类型", None, None

        doc_id, title_id, text_type, page_number, page_type = fulltext_info

        cursor.execute("SELECT doc_title FROM documents WHERE doc_id = %s", (doc_id,))
        doc_title = cursor.fetchone()
        doc_title = doc_title[0] if doc_title else "未知文献"

        cursor.execute("SELECT title_name FROM titles WHERE title_id = %s", (title_id,))
        title_name = cursor.fetchone()
        title_name = title_name[0] if title_name else "未知标题"

        # 获取page_id
        page_id = None
        if page_number and page_type:
            cursor.execute("""
                SELECT page_id
                FROM pages
                WHERE doc_id = %s AND page_number = %s AND page_type = %s
                LIMIT 1
            """, (doc_id, page_number, page_type))
            page_row = cursor.fetchone()
            page_id = page_row[0] if page_row else None

        return doc_title, title_name, text_type, page_id, doc_id
    except Exception as e:
        print(f"获取文本信息失败: {str(e)}")
        return "数据库查询错误", "数据库查询错误", "错误", None, None

def get_fulltext_id_from_mysql(cursor, query_text):
    """根据文本内容查找对应的全文ID"""
    try:
        sql = """
            SELECT full_text_id
            FROM full_text_1
            WHERE MATCH(full_text) AGAINST(%s IN BOOLEAN MODE)
            LIMIT 1
        """
        cursor.execute(sql, (query_text,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"获取全文ID失败: {str(e)}")
        return None

@csrf_exempt
@require_http_methods(['POST'])
def get_compare_texts(request):
    """批量获取对比阅读所需的全文内容"""
    try:
        data = json.loads(request.body)
        items = data.get('items', [])

        if not items:
            return JsonResponse({
                'success': False,
                'error': '没有提供要获取的文本项'
            })

        # 获取数据库连接
        conn = get_mysql_connection()
        cursor = conn.cursor()

        try:
            texts = []
            for item in items:
                doc_id = item.get('doc_id')
                page_id = item.get('page_id')
                title_id = item.get('title_id')
                page_number = item.get('page_number')
                page_type = item.get('page_type')
                full_text_id = item.get('fulltext_id')

                print(f"处理文本项: doc_id={doc_id}, title_id={title_id}, page_number={page_number}, page_type={page_type}, page_id={page_id}")

                # 策略1: 通过title_id、page_number和page_type精确定位
                if title_id and page_number and page_type:
                    print("使用策略1: 通过title_id、page_number和page_type精确定位")
                    cursor.execute("""
                        SELECT p.page_id, p.full_text_id_list, p.doc_id,
                               d.doc_title, d.dynasty, d.doc_specific_category, d.doc_theme,
                               t.title_name, a.author_name
                        FROM pages p
                        JOIN documents d ON d.doc_id = p.doc_id
                        LEFT JOIN document_author_links dal ON dal.doc_id = d.doc_id
                        LEFT JOIN authors a ON a.author_id = dal.author_id
                        LEFT JOIN titles t ON t.title_id = %s
                        WHERE p.title_id = %s
                        AND p.page_number = %s
                        AND p.page_type = %s
                    """, (title_id, title_id, page_number, page_type))

                    page_result = cursor.fetchone()
                    if page_result:
                        page_id = page_result['page_id']
                        full_text_id_list = page_result['full_text_id_list']
                        doc_id = page_result['doc_id']
                        doc_title = page_result['doc_title']
                        dynasty = page_result['dynasty']
                        author_name = page_result['author_name']
                        doc_specific_category = page_result['doc_specific_category']
                        doc_theme = page_result['doc_theme']
                        title_name = page_result['title_name']
                        print(f"找到页面: page_id={page_id}, full_text_ids={full_text_id_list}")
                    else:
                        print("未找到匹配的页面")
                        continue


                # 策略2: 通过page_id直接获取
                elif full_text_id:
                    print("使用策略2: 通过full_text_id直接获取")
                    cursor.execute("""
                        SELECT p.page_id, p.full_text_id_list, p.page_number, p.page_type, p.doc_id,
                               d.doc_title, d.dynasty, d.doc_specific_category, d.doc_theme,
                               t.title_name, a.author_name
                        FROM pages p
                        JOIN full_text_1 ft ON ft.full_text_id = %s
                        JOIN documents d ON d.doc_id = ft.doc_id
                        JOIN document_author_links dal ON dal.doc_id = d.doc_id
                        JOIN authors a ON a.author_id = dal.author_id
                        LEFT JOIN titles t ON t.title_id = ft.title_id
                        WHERE p.doc_id = ft.doc_id
                        AND p.page_number = ft.page_number
                        AND p.page_type = ft.page_type
                    """, (full_text_id,))

                    page_result = cursor.fetchone()
                    if not page_result or not page_result['full_text_id_list']:
                        print(f"未找到page_id={page_id}的页面")
                        continue
                    full_text_id_list = page_result['full_text_id_list']
                    page_number = page_result['page_number']
                    page_type = page_result['page_type']
                    doc_id = page_result['doc_id']
                    doc_title = page_result['doc_title']
                    dynasty = page_result['dynasty']
                    author_name = page_result['author_name']
                    doc_specific_category = page_result['doc_specific_category']
                    doc_theme = page_result['doc_theme']
                    title_name = page_result['title_name']

                else:
                    print("缺少必要的定位信息")
                    continue

                # 获取所有相关的全文内容
                full_text_ids = full_text_id_list.split(',')
                placeholders = ','.join(['%s'] * len(full_text_ids))

                cursor.execute(f"""
                    SELECT ft.full_text_id, ft.full_text, ft.text_type, ft.full_text_order,
                           ft.related_id, t.title_name
                    FROM full_text_1 ft
                    LEFT JOIN titles t ON ft.title_id = t.title_id
                    WHERE ft.full_text_id IN ({placeholders})
                    ORDER BY ft.full_text_order
                """, tuple(full_text_ids))

                full_texts = cursor.fetchall()
                print(f"获取到{len(full_texts)}条文本记录")

                # 组织返回数据
                texts.append({
                    'page_id': page_id,
                    'doc_id': doc_id,
                    'title_id': title_id,
                    'page_number': page_number,
                    'page_type': page_type,
                    'doc_title': doc_title,
                    'dynasty': dynasty,
                    'author_name': author_name,
                    'doc_specific_category': doc_specific_category,
                    'doc_theme': doc_theme,
                    'title_name': title_name,
                    'full_texts': [{
                        'text': text['full_text'],
                        'text_type': text['text_type'],
                        'text_id': text['full_text_id'],
                        'related_id': text['related_id'],
                        'title_name': text['title_name']
                    } for text in full_texts]
                })

            print(f"总共处理了{len(texts)}个页面的文本")
            return JsonResponse({
                'success': True,
                'texts': texts
            })

        finally:
            cursor.close()
            conn.close()

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': '无效的JSON数据'
        }, status=400)
    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
