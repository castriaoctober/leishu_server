from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import pymysql
from utils.database import connect_db
import json
import logging
import warnings
from elasticsearch import ElasticsearchWarning

# 配置日志
logger = logging.getLogger(__name__)

# 忽略Elasticsearch安全警告
warnings.filterwarnings("ignore", category=ElasticsearchWarning)

# 数据库连接配置
DB_CONFIG = settings.DB_CONFIG

# 初始化Elasticsearch客户端
ES_CONFIG = settings.ES_CONFIG
es = Elasticsearch(**ES_CONFIG)

# 索引名称
INDEX_NAME = 'leishu_yongle_index'

@csrf_exempt
def create_es_index(request):
    """创建Elasticsearch索引，设置映射"""
    try:
        # 检查索引是否存在，如果存在则删除
        if es.indices.exists(index=INDEX_NAME):
            es.indices.delete(index=INDEX_NAME)

        # 创建索引并定义映射
        mapping = {
            "settings": {
                "analysis": {
                    "analyzer": {
                        "chinese_analyzer": {
                            "type": "custom",
                            "tokenizer": "ik_max_word",
                            "filter": ["lowercase"]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "doc_id": {"type": "integer"},
                    "doc_title": {"type": "text", "analyzer": "chinese_analyzer"},
                    "doc_origin_id": {"type": "text", "analyzer": "chinese_analyzer"},
                    "doc_image": {"type": "text"},
                    "dynasty": {"type": "keyword"},
                    "category_type": {"type": "keyword"},
                    "doc_specific_category": {"type": "keyword"},
                    "doc_style": {"type": "keyword"},
                    "doc_theme": {"type": "keyword"},
                    "compilation_time": {"type": "text", "analyzer": "chinese_analyzer"},
                    "printing_time": {"type": "text", "analyzer": "chinese_analyzer"},
                    "publication_time": {"type": "text", "analyzer": "chinese_analyzer"},
                    "doc_type": {"type": "keyword"},
                    "completeness": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "title_name": {"type": "text", "analyzer": "chinese_analyzer"},
                    "title_level": {"type": "keyword"},
                    "full_text": {"type": "text", "analyzer": "chinese_analyzer"},
                    "page_number": {"type": "integer"},
                    "author_name": {"type": "text", "analyzer": "chinese_analyzer"}
                }
            }
        }

        es.indices.create(index=INDEX_NAME, body=mapping)
        logger.info(f"索引 {INDEX_NAME} 创建成功")
        return JsonResponse({'status': 'success', 'message': f'索引 {INDEX_NAME} 创建成功'})
    except Exception as e:
        logger.error(f"创建索引失败: {e}")
        return JsonResponse({'status': 'error', 'message': f'创建索引失败: {str(e)}'}, status=500)

@csrf_exempt
def sync_data(request):
    conn = None
    """同步所有数据到Elasticsearch"""
    try:
        # 确保这里不传递request参数
        conn = connect_db()
        with conn.cursor() as cursor:
            # 获取所有文档ID
            cursor.execute("SELECT doc_id FROM documents")
            document_ids = [row[0] for row in cursor.fetchall()]
            logger.info(f"找到 {len(document_ids)} 个文档")

            actions = []
            for doc_id in document_ids:
                # 获取文档基本信息
                cursor.execute("""
                    SELECT doc_id, doc_title, doc_origin_id, doc_image, dynasty,
                           category_type, doc_specific_category, doc_style, doc_theme,
                           compilation_time, printing_time, publication_time, doc_type,
                           completeness, source
                    FROM documents
                    WHERE doc_id = %s
                """, (doc_id,))

                doc_info = cursor.fetchone()
                if not doc_info:
                    continue

                doc_id, doc_title, doc_origin_id, doc_image, dynasty, category_type, specific_category, doc_style, doc_theme, compile_time, printing_time, pub_time, doc_type, completeness, source = doc_info

                # 获取作者信息
                cursor.execute("""
                    SELECT a.author_name
                    FROM authors a
                    JOIN document_author_links dal ON a.author_id = dal.author_id
                    WHERE dal.doc_id = %s
                """, (doc_id,))

                author_rows = cursor.fetchall()
                author_names = ", ".join([row[0] for row in author_rows]) if author_rows else ""

                # 获取标题
                cursor.execute("""
                    SELECT title_id, title_name, title_level
                    FROM titles
                    WHERE doc_id = %s
                    ORDER BY title_order
                """, (doc_id,))

                titles = cursor.fetchall()
                title_name = titles[0][1] if titles else ""
                title_level = titles[0][2] if titles else ""

                # 获取全文内容 - 首先尝试通过title_id获取
                cursor.execute("""
                    SELECT ft.full_text
                    FROM full_text_1 ft
                    WHERE ft.title_id IN (
                        SELECT title_id FROM titles WHERE doc_id = %s
                    )
                """, (doc_id,))

                full_text_rows = cursor.fetchall()
                full_text = " ".join([row[0] for row in full_text_rows if row[0]]) if full_text_rows else ""

                # 如果通过title_id找不到文本，尝试通过pages表查找
                if not full_text:
                    cursor.execute("""
                        SELECT ft.full_text
                        FROM full_text_1 ft
                        JOIN pages p ON ft.full_text_id = p.full_text_id_list
                        WHERE p.doc_id = %s
                    """, (doc_id,))

                    full_text_rows = cursor.fetchall()
                    full_text = " ".join([row[0] for row in full_text_rows if row[0]]) if full_text_rows else ""

                # 获取页码信息
                cursor.execute("""
                    SELECT page_number
                    FROM pages
                    WHERE doc_id = %s
                    LIMIT 1
                """, (doc_id,))

                page_row = cursor.fetchone()
                page_number = page_row[0] if page_row else 0

                action = {
                    "_index": INDEX_NAME,
                    "_id": doc_id,
                    "_source": {
                        "doc_id": doc_id,
                        "doc_title": doc_title if doc_title else "",
                        "doc_origin_id": doc_origin_id if doc_origin_id else "",
                        "doc_image": doc_image if doc_image else "",
                        "dynasty": dynasty if dynasty else "",
                        "category_type": category_type if category_type else "",
                        "doc_specific_category": specific_category if specific_category else "",
                        "doc_style": doc_style if doc_style else "",
                        "doc_theme": doc_theme if doc_theme else "",
                        "compilation_time": compile_time if compile_time else "",
                        "printing_time": printing_time if printing_time else "",
                        "publication_time": pub_time if pub_time else "",
                        "doc_type": doc_type if doc_type else "",
                        "completeness": completeness if completeness else "",
                        "source": source if source else "",
                        "title_name": title_name,
                        "title_level": title_level,
                        "full_text": full_text,
                        "page_number": page_number,
                        "author_name": author_names
                    }
                }

                actions.append(action)

                # 每1000个文档批量导入一次
                if len(actions) >= 1000:
                    success, failed = bulk(es, actions, raise_on_error=False)
                    logger.info(f"已导入 {success} 条文档，失败 {len(failed) if failed else 0} 条")
                    actions = []

            # 导入剩余的文档
            if actions:
                success, failed = bulk(es, actions, raise_on_error=False)
                logger.info(f"最终导入 {success} 条文档，失败 {len(failed) if failed else 0} 条")

            # 刷新索引以确保数据可见
            es.indices.refresh(index=INDEX_NAME)

            # 返回成功响应
            return JsonResponse({
               'status':'success',
               'message': f'成功同步 {len(document_ids)} 个文档到Elasticsearch',
                'total': len(document_ids),
               'success': success,
                'failed': len(failed) if failed else 0
            })
    except Exception as e:
        logger.error(f"同步数据失败: {e}")
        # 返回错误响应
        return JsonResponse({
           'status': 'error',
           'message': f'同步数据失败: {str(e)}'
        }, status=500)
    finally:
        if conn:
            conn.close()

@csrf_exempt
def sync_incremental_data(request):
    """增量同步新数据到Elasticsearch"""
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            # 获取已索引的文档ID
            try:
                # 获取ES中已有的文档数量
                es_stats = es.count(index=INDEX_NAME)
                es_count = es_stats["count"]

                # 如果ES中没有文档，执行全量同步
                if es_count == 0:
                    logger.info("ES索引为空，执行全量同步")
                    return sync_data()

                # 获取ES中存在的所有文档ID
                es_query = {
                    "query": {"match_all": {}},
                    "size": 10000,  # ES默认最多返回10000条
                    "_source": ["doc_id"]
                }

                es_response = es.search(index=INDEX_NAME, body=es_query)
                indexed_doc_ids = set(hit["_source"]["doc_id"] for hit in es_response["hits"]["hits"])

                logger.info(f"已在ES索引中找到 {len(indexed_doc_ids)} 个文档")

                # 获取MySQL中所有文档ID
                cursor.execute("SELECT doc_id FROM documents")
                mysql_doc_ids = set(row[0] for row in cursor.fetchall())

                logger.info(f"MySQL中共有 {len(mysql_doc_ids)} 个文档")

                # 找出需要新增的文档
                new_doc_ids = mysql_doc_ids - indexed_doc_ids

                logger.info(f"需要新增 {len(new_doc_ids)} 个文档到ES")

                if not new_doc_ids:
                    logger.info("没有新的文档需要同步")
                    return True

                # 同步新文档
                actions = []
                for doc_id in new_doc_ids:
                    # 获取文档基本信息
                    cursor.execute("""
                        SELECT doc_id, doc_title, doc_origin_id, doc_image, dynasty,
                               category_type, doc_specific_category, doc_style, doc_theme,
                               compilation_time, printing_time, publication_time, doc_type,
                               completeness, source
                        FROM documents
                        WHERE doc_id = %s
                    """, (doc_id,))

                    doc_info = cursor.fetchone()
                    if not doc_info:
                        continue

                    doc_id, doc_title, doc_origin_id, doc_image, dynasty, category_type, specific_category, doc_style, doc_theme, compile_time, printing_time, pub_time, doc_type, completeness, source = doc_info

                    # 获取作者信息
                    cursor.execute("""
                        SELECT a.author_name
                        FROM authors a
                        JOIN document_author_links dal ON a.author_id = dal.author_id
                        WHERE dal.doc_id = %s
                    """, (doc_id,))

                    author_rows = cursor.fetchall()
                    author_names = ", ".join([row[0] for row in author_rows]) if author_rows else ""

                    # 获取标题
                    cursor.execute("""
                        SELECT title_id, title_name, title_level
                        FROM titles
                        WHERE doc_id = %s
                        ORDER BY title_order
                    """, (doc_id,))

                    titles = cursor.fetchall()
                    title_name = titles[0][1] if titles else ""
                    title_level = titles[0][2] if titles else ""

                    # 获取全文内容 - 首先尝试通过title_id获取
                    cursor.execute("""
                        SELECT ft.full_text
                        FROM full_text_1 ft
                        WHERE ft.title_id IN (
                            SELECT title_id FROM titles WHERE doc_id = %s
                        )
                    """, (doc_id,))

                    full_text_rows = cursor.fetchall()
                    full_text = " ".join([row[0] for row in full_text_rows if row[0]]) if full_text_rows else ""

                    # 如果通过title_id找不到文本，尝试通过pages表查找
                    if not full_text:
                        cursor.execute("""
                            SELECT ft.full_text
                            FROM full_text_1 ft
                            JOIN pages p ON ft.full_text_id = p.full_text_id_list
                            WHERE p.doc_id = %s
                        """, (doc_id,))

                        full_text_rows = cursor.fetchall()
                        full_text = " ".join([row[0] for row in full_text_rows if row[0]]) if full_text_rows else ""

                    # 获取页码信息
                    cursor.execute("""
                        SELECT page_number
                        FROM pages
                        WHERE doc_id = %s
                        LIMIT 1
                    """, (doc_id,))

                    page_row = cursor.fetchone()
                    page_number = page_row[0] if page_row else 0

                    action = {
                        "_index": INDEX_NAME,
                        "_id": doc_id,
                        "_source": {
                            "doc_id": doc_id,
                            "doc_title": doc_title if doc_title else "",
                            "doc_origin_id": doc_origin_id if doc_origin_id else "",
                            "doc_image": doc_image if doc_image else "",
                            "dynasty": dynasty if dynasty else "",
                            "category_type": category_type if category_type else "",
                            "doc_specific_category": specific_category if specific_category else "",
                            "doc_style": doc_style if doc_style else "",
                            "doc_theme": doc_theme if doc_theme else "",
                            "compilation_time": compile_time if compile_time else "",
                            "printing_time": printing_time if printing_time else "",
                            "publication_time": pub_time if pub_time else "",
                            "doc_type": doc_type if doc_type else "",
                            "completeness": completeness if completeness else "",
                            "source": source if source else "",
                            "title_name": title_name,
                            "title_level": title_level,
                            "full_text": full_text,
                            "page_number": page_number,
                            "author_name": author_names
                        }
                    }

                    actions.append(action)

                    # 每500个文档批量导入一次
                    if len(actions) >= 500:
                        success, failed = bulk(es, actions, raise_on_error=False)
                        logger.info(f"已导入 {success} 条文档，失败 {len(failed) if failed else 0} 条")
                        actions = []

                # 导入剩余的文档
                if actions:
                    success, failed = bulk(es, actions, raise_on_error=False)
                    logger.info(f"最终导入 {success} 条文档，失败 {len(failed) if failed else 0} 条")

                # 刷新索引以确保数据可见
                es.indices.refresh(index=INDEX_NAME)
                return True

            except Exception as e:
                logger.error(f"增量同步过程中出错: {e}")
                # 如果增量同步失败，尝试全量同步
                logger.info("尝试执行全量同步")
                return sync_data()
    except Exception as e:
        logger.error(f"增量同步数据失败: {e}")
        return False
    finally:
        conn.close()

@csrf_exempt
@require_http_methods(["POST"])
def search(request):
    """API端点：执行搜索并返回结果"""
    try:
        data = json.loads(request.body)
        search_type = data.get('search_type', 'basic')
        query_text = data.get('query', '')
        filters = data.get('filters', {})

        logger.info(f"执行{search_type}搜索，关键词：'{query_text}'，过滤条件：{filters}")

        # 根据搜索类型执行不同的搜索
        if search_type == 'basic':
            results = basic_search(query_text, filters)
        elif search_type == 'fulltext':
            results = fulltext_search(query_text, filters)
        elif search_type == 'fuzzy':
            results = fuzzy_search(query_text, filters)
        elif search_type == 'highlight':
            results = highlight_search(query_text, filters)
        elif search_type == 'variant':
            results = variant_search(query_text, filters)
        else:
            return JsonResponse({"error": "不支持的搜索类型"}, status=400)

        logger.info(f"搜索结果：找到 {results['total']} 条匹配结果")
        return JsonResponse(results)
    except Exception as e:
        logger.error(f"搜索出错: {e}")
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def basic_search(query, filters=None):
    """基本检索：精确匹配指定字段"""
    must_conditions = []

    # 如果没有查询词，返回所有文档
    if not query:
        must_conditions.append({
            "match_all": {}
        })
    else:
        # 添加主查询条件
        must_conditions.append({
            "multi_match": {
                "query": query,
                "fields": ["doc_title", "category_type", "doc_type",
                           "title_name", "full_text", "author_name"]
            }
        })

    # 添加过滤条件
    if filters:
        for field, value in filters.items():
            if value:
                if field in ['compilation_time', 'printing_time', 'publication_time'] and isinstance(value, dict):
                    must_conditions.append({
                        "range": {
                            field: {
                                "gte": value.get('from', ''),
                                "lte": value.get('to', '')
                            }
                        }
                    })
                else:
                    must_conditions.append({
                        "match": {
                            field: value
                        }
                    })

    # 构建查询
    query_body = {
        "query": {
            "bool": {
                "must": must_conditions
            }
        },
        "size": 100  # 限制返回结果数量
    }

    logger.debug(f"基本搜索查询：{json.dumps(query_body)}")

    # 执行查询
    response = es.search(index=INDEX_NAME, body=query_body)

    # 解析结果
    results = []
    for hit in response['hits']['hits']:
        source = hit['_source']
        results.append({
            "score": hit['_score'],
            "doc_id": source['doc_id'],
            "doc_title": source['doc_title'],
            "dynasty": source.get('dynasty', ''),
            "category_type": source['category_type'],
            "doc_type": source['doc_type'],
            "page_number": source['page_number'],
            "content_preview": source['full_text'][:200] + "..." if source['full_text'] and len(
                source['full_text']) > 200 else source['full_text']
        })

    return {
        "total": response['hits']['total']['value'],
        "results": results
    }

@csrf_exempt
def fulltext_search(query, filters=None):
    """全文检索：在所有文本字段中搜索"""
    must_conditions = []

    # 如果没有查询词，返回所有文档
    if not query:
        must_conditions.append({
            "match_all": {}
        })
    else:
        # 添加全文搜索条件
        must_conditions.append({
            "multi_match": {
                "query": query,
                "fields": ["doc_title", "category_type", "doc_type",
                           "title_name", "full_text", "author_name"],
                "type": "best_fields",
                "tie_breaker": 0.3
            }
        })

    # 添加过滤条件
    if filters:
        for field, value in filters.items():
            if value:
                if field in ['compilation_time', 'printing_time', 'publication_time'] and isinstance(value, dict):
                    must_conditions.append({
                        "range": {
                            field: {
                                "gte": value.get('from', ''),
                                "lte": value.get('to', '')
                            }
                        }
                    })
                else:
                    must_conditions.append({
                        "match": {
                            field: value
                        }
                    })

    # 构建查询
    query_body = {
        "query": {
            "bool": {
                "must": must_conditions
            }
        },
        "size": 100
    }

    logger.debug(f"全文搜索查询：{json.dumps(query_body)}")

    # 执行查询
    response = es.search(index=INDEX_NAME, body=query_body)

    # 解析结果
    results = []
    for hit in response['hits']['hits']:
        source = hit['_source']
        results.append({
            "score": hit['_score'],
            "doc_id": source['doc_id'],
            "doc_title": source['doc_title'],
            "dynasty": source.get('dynasty', ''),
            "category_type": source['category_type'],
            "doc_type": source['doc_type'],
            "page_number": source['page_number'],
            "content_preview": source['full_text'][:200] + "..." if source['full_text'] and len(
                source['full_text']) > 200 else source['full_text']
        })

    return {
        "total": response['hits']['total']['value'],
        "results": results
    }

@csrf_exempt
def fuzzy_search(query, filters=None):
    """模糊检索：使用模糊匹配和通配符搜索"""
    must_conditions = []

    # 如果没有查询词，返回所有文档
    if not query:
        must_conditions.append({
            "match_all": {}
        })
    else:
        # 添加模糊搜索条件
        should_conditions = [
            # 模糊匹配标题
            {
                "fuzzy": {
                    "doc_title": {
                        "value": query,
                        "fuzziness": "AUTO"
                    }
                }
            },
            # 模糊匹配全文
            {
                "fuzzy": {
                    "full_text": {
                        "value": query,
                        "fuzziness": "AUTO"
                    }
                }
            },
            # 模糊匹配标题字段
            {
                "fuzzy": {
                    "title_name": {
                        "value": query,
                        "fuzziness": "AUTO"
                    }
                }
            },
            # 通配符搜索
            {
                "wildcard": {
                    "doc_title": f"*{query}*"
                }
            },
            {
                "wildcard": {
                    "full_text": f"*{query}*"
                }
            }
        ]

        must_conditions.append({
            "bool": {
                "should": should_conditions,
                "minimum_should_match": 1
            }
        })

    # 添加过滤条件
    if filters:
        for field, value in filters.items():
            if value:
                if field in ['compilation_time', 'printing_time', 'publication_time'] and isinstance(value, dict):
                    must_conditions.append({
                        "range": {
                            field: {
                                "gte": value.get('from', ''),
                                "lte": value.get('to', '')
                            }
                        }
                    })
                else:
                    must_conditions.append({
                        "match": {
                            field: value
                        }
                    })

    # 构建查询
    query_body = {
        "query": {
            "bool": {
                "must": must_conditions
            }
        },
        "size": 100
    }

    logger.debug(f"模糊搜索查询：{json.dumps(query_body)}")

    # 执行查询
    response = es.search(index=INDEX_NAME, body=query_body)

    # 解析结果
    results = []
    for hit in response['hits']['hits']:
        source = hit['_source']
        results.append({
            "score": hit['_score'],
            "doc_id": source['doc_id'],
            "doc_title": source['doc_title'],
            "dynasty": source.get('dynasty', ''),
            "category_type": source['category_type'],
            "doc_type": source['doc_type'],
            "page_number": source['page_number'],
            "content_preview": source['full_text'][:200] + "..." if source['full_text'] and len(
                source['full_text']) > 200 else source['full_text']
        })

    return {
        "total": response['hits']['total']['value'],
        "results": results
    }

@csrf_exempt
def highlight_search(query, filters=None):
    """高亮检索：返回带高亮标记的搜索结果"""
    must_conditions = []

    # 如果没有查询词，返回所有文档
    if not query:
        must_conditions.append({
            "match_all": {}
        })
    else:
        # 添加搜索条件
        must_conditions.append({
            "multi_match": {
                "query": query,
                "fields": ["doc_title", "category_type", "doc_type",
                           "title_name", "full_text", "author_name"],
            }
        })

    # 添加过滤条件
    if filters:
        for field, value in filters.items():
            if value:
                if field in ['compilation_time', 'printing_time', 'publication_time'] and isinstance(value, dict):
                    must_conditions.append({
                        "range": {
                            field: {
                                "gte": value.get('from', ''),
                                "lte": value.get('to', '')
                            }
                        }
                    })
                else:
                    must_conditions.append({
                        "match": {
                            field: value
                        }
                    })

    # 构建查询
    query_body = {
        "query": {
            "bool": {
                "must": must_conditions
            }
        },
        "highlight": {
            "pre_tags": ["<em class='highlight'>"],
            "post_tags": ["</em>"],
            "fields": {
                "doc_title": {},
                "title_name": {},
                "full_text": {
                    "fragment_size": 150,
                    "number_of_fragments": 3
                },
                "author_name": {}
            }
        },
        "size": 100
    }

    logger.debug(f"高亮搜索查询：{json.dumps(query_body)}")

    # 执行查询
    response = es.search(index=INDEX_NAME, body=query_body)

    # 解析结果
    results = []
    for hit in response['hits']['hits']:
        source = hit['_source']
        highlight = hit.get('highlight', {})

        # 获取高亮字段，如果没有高亮则使用原始内容
        title_highlight = highlight.get('doc_title', [source['doc_title']])[0] if source[
            'doc_title'] else ""
        content_highlight = " ... ".join(highlight.get('full_text', [])) if 'full_text' in highlight else (
            source['full_text'][:200] + "..." if source['full_text'] and len(source['full_text']) > 200 else source[
                'full_text'])

        results.append({
            "score": hit['_score'],
            "doc_id": source['doc_id'],
            "doc_title": title_highlight,
            "dynasty": source.get('dynasty', ''),
            "category_type": source['category_type'],
            "doc_type": source['doc_type'],
            "page_number": source['page_number'],
            "content_preview": content_highlight,
            "has_highlight": bool(highlight)
        })

    return {
        "total": response['hits']['total']['value'],
        "results": results
    }

@csrf_exempt
def variant_search(query, filters=None):
    """异文检索：查找可能是异文的内容，包含高亮功能"""
    must_conditions = []

    if not query:
        return {
            "total": 0,
            "results": [],
            "error": "异文检索需要输入查询词"
        }

    # 对于异文检索，设计智能查询策略
    # 1. 精确词组查询 - 寻找完全匹配的短语
    # 2. 模糊匹配 - 寻找相似但不完全相同的文本
    # 3. 同义词扩展 - 使用ES的同义词功能

    should_conditions = [
        # 精确短语匹配
        {
            "match_phrase": {
                "full_text": {
                    "query": query,
                    "slop": 0,  # 不允许词条之间有间隔
                    "boost": 10  # 提高精确匹配的权重
                }
            }
        },
        # 近似短语匹配
        {
            "match_phrase": {
                "full_text": {
                    "query": query,
                    "slop": 2,  # 允许词条之间有少量间隔
                    "boost": 5
                }
            }
        },
        # 标准匹配 - 允许词条出现在文档中的任何位置
        {
            "match": {
                "full_text": {
                    "query": query,
                    "minimum_should_match": "75%",
                    "boost": 1
                }
            }
        },
        # 对于较短的查询词，使用模糊匹配找出可能的异文
        {
            "fuzzy": {
                "full_text": {
                    "value": query,
                    "fuzziness": "AUTO",
                    "boost": 0.5
                }
            }
        }
    ]

    must_conditions.append({
        "bool": {
            "should": should_conditions,
            "minimum_should_match": 1
        }
    })

    # 添加过滤条件
    if filters:
        for field, value in filters.items():
            if value and field not in ['show_context']:  # 排除非过滤字段
                if field in ['compilation_time', 'printing_time', 'publication_time'] and isinstance(value, dict):
                    must_conditions.append({
                        "range": {
                            field: {
                                "gte": value.get('from', ''),
                                "lte": value.get('to', '')
                            }
                        }
                    })
                else:
                    must_conditions.append({
                        "match": {
                            field: value
                        }
                    })

    # 构建查询
    query_body = {
        "query": {
            "bool": {
                "must": must_conditions
            }
        },
        "highlight": {
            "pre_tags": ["<em class='highlight'>"],
            "post_tags": ["</em>"],
            "fields": {
                "full_text": {
                    "fragment_size": 200,
                    "number_of_fragments": 1
                }
            }
        },
        "size": 100
    }

    logger.debug(f"异文查询：{json.dumps(query_body)}")

    # 执行查询
    response = es.search(index=INDEX_NAME, body=query_body)

    # 解析结果
    results = []
    conn = None
    try:
        conn = connect_db()
        with conn.cursor() as cursor:
            for hit in response['hits']['hits']:
                source = hit['_source']
                highlight = hit.get('highlight', {})

                # 获取page_id和title_id
                cursor.execute("""
                    SELECT p.page_id, p.title_id, p.page_type, p.full_text_id_list
                    FROM pages p
                    WHERE p.doc_id = %s AND p.page_number = %s
                    LIMIT 1
                """, (source['doc_id'], source['page_number']))
                page_result = cursor.fetchone()

                page_id = page_result[0] if page_result else None
                title_id = page_result[1] if page_result else None
                page_type = page_result[2] if page_result else None
                fulltext_id = page_result[3] if page_result else None

                # 获取作者信息
                cursor.execute("""
                    SELECT GROUP_CONCAT(a.author_name) as author_names
                    FROM authors a
                    JOIN document_author_links dal ON a.author_id = dal.author_id
                    WHERE dal.doc_id = %s
                """, (source['doc_id'],))
                author_result = cursor.fetchone()
                author_name = author_result[0] if author_result else ""

                # 显示上下文设置
                show_context = filters.get('show_context', True) if filters else True

                # 从全文中提取最相似的片段作为可能的异文
                full_text = source['full_text']
                content_highlight = " ... ".join(highlight.get('full_text', [])) if 'full_text' in highlight else ""

                # 如果没有高亮结果，尝试手动查找相似片段
                if not content_highlight and full_text:
                    variant_text = extract_similar_text(full_text, query, context_size=50 if show_context else 0)
                else:
                    variant_text = content_highlight

                # 预览内容展示
                if show_context:
                    content_preview = variant_text if variant_text else (
                        full_text[:200] + "..." if len(full_text) > 200 else full_text)
                else:
                    # 如果不显示上下文，只显示查找到的异文
                    content_preview = "..." if variant_text else "未找到明显的异文"

                results.append({
                    "score": hit['_score'],
                    "doc_id": source['doc_id'],
                    "doc_title": source['doc_title'],
                    "dynasty": source.get('dynasty', ''),
                    "category_type": source['category_type'],
                    "doc_type": source['doc_type'],
                    "doc_specific_category": source.get('doc_specific_category', ''),
                    "doc_theme": source.get('doc_theme', ''),
                    "page_number": source['page_number'],
                    "page_id": page_id,
                    "title_id": title_id,
                    "page_type": page_type,
                    "fulltext_id": fulltext_id,
                    "author_name": author_name,
                    "content_preview": content_preview,
                    "variant_text": variant_text,
                    "has_highlight": bool(highlight),
                    "sentence": variant_text  # 用于高亮显示的匹配句段
                })
    except Exception as e:
        logger.error(f"获取额外数据时出错: {e}")
        # 如果获取额外数据失败，仍然返回基本信息
        for hit in response['hits']['hits']:
            source = hit['_source']
            highlight = hit.get('highlight', {})
            # ... 原有的结果处理逻辑 ...
            results.append({
                "score": hit['_score'],
                "doc_id": source['doc_id'],
                "doc_title": source['doc_title'],
                "dynasty": source.get('dynasty', ''),
                "category_type": source['category_type'],
                "doc_type": source['doc_type'],
                "doc_specific_category": source.get('doc_specific_category', ''),
                "doc_theme": source.get('doc_theme', ''),
                "page_number": source['page_number'],
                "page_id": None,
                "title_id": None,
                "page_type": None,
                "fulltext_id": None,
                "author_name": "",
                "content_preview": content_preview,
                "variant_text": variant_text,
                "has_highlight": bool(highlight),
                "sentence": variant_text
            })
    finally:
        if conn:
            conn.close()

    return {
        "total": response['hits']['total']['value'],
        "results": results
    }

@csrf_exempt
def extract_similar_text(full_text, query, context_size=50):
    """从全文中提取与查询最相似的片段"""
    if not full_text or not query:
        return ""

    # 简单实现：查找包含查询中词语最多的文本片段
    # 在实际应用中，可能需要更复杂的算法来找到最相似的文本

    # 将查询和全文分词
    query_chars = set(query)

    max_similarity = 0
    best_match = ""
    best_start = 0

    # 滑动窗口查找最相似片段
    window_size = min(len(query) * 2, len(full_text))
    for i in range(0, len(full_text) - window_size + 1):
        window = full_text[i:i + window_size]
        window_chars = set(window)

        # 计算相似度（简化为字符重叠数量）
        similarity = len(query_chars.intersection(window_chars)) / len(query_chars)

        if similarity > max_similarity:
            max_similarity = similarity
            best_match = window
            best_start = i

    # 如果找到匹配并且要显示上下文
    if best_match and context_size > 0:
        # 扩展上下文
        start = max(0, best_start - context_size)
        end = min(len(full_text), best_start + window_size + context_size)
        context = full_text[start:end]
        return context

    return best_match


# 重新索引API
@csrf_exempt
@require_http_methods(["POST"])
def reindex(request):
    """重新创建索引并同步数据"""
    try:
        # 创建索引
        index_created = create_es_index()
        if not index_created:
            return JsonResponse({"success": False, "error": "索引创建失败"}, status=500)

        # 同步数据
        sync_success = sync_data()
        if not sync_success:
            return JsonResponse({"success": False, "error": "数据同步失败"}, status=500)

        return JsonResponse({
            "success": True,
            "message": "重新索引完成"
        })
    except Exception as e:
        logger.error(f"重新索引失败: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_sync_data(request):
    """API端点：同步数据到ES"""
    try:
        data = json.loads(request.body)
        sync_type = data.get('type', 'incremental') if data else 'incremental'

        if sync_type == 'full':
            success = sync_data(request)
        else:
            success = sync_incremental_data(request)

        if success:
            conn = connect_db()
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM documents")
                mysql_count = cursor.fetchone()[0]

                es_stats = es.count(index=INDEX_NAME)
                es_count = es_stats["count"]

            conn.close()

            return JsonResponse({
                "success": True,
                "message": f"数据同步成功，MySQL有{mysql_count}个文档，ES索引有{es_count}个文档",
                "mysql_count": mysql_count,
                "es_count": es_count
            })
        else:
            return JsonResponse({
                "success": False,
                "message": "数据同步失败，请查看服务器日志"
            }, status=500)
    except Exception as e:
        logger.error(f"同步数据API调用失败: {e}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@require_http_methods(["GET"])
def get_database_info(request):
    """获取数据库信息"""
    conn = None
    try:
        conn = connect_db()
        info = {}

        with conn.cursor() as cursor:
            tables = ['documents', 'pages', 'full_text_1', 'titles', 'authors', 'users', 'bookmarks']
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                info[f"{table}_count"] = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) FROM documents d
                WHERE NOT EXISTS (SELECT 1 FROM pages p WHERE p.doc_id = d.doc_id)
            """)
            info["documents_without_pages"] = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) FROM pages p
                WHERE p.full_text_id_list IS NULL
            """)
            info["pages_without_fulltext"] = cursor.fetchone()[0]

            try:
                es_stats = es.count(index=INDEX_NAME)
                info["es_doc_count"] = es_stats["count"]
            except:
                info["es_doc_count"] = 0

        return JsonResponse({"success": True, "info": info})
    except Exception as e:
        logger.error(f"获取数据库信息失败: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
    finally:
        if conn:
            conn.close()

@csrf_exempt
@require_http_methods(["POST"])
def api_variant_search(request):
    """异文检索专用API端点"""
    try:
        data = json.loads(request.body)
        query_text = data.get('query', '')
        filters = data.get('filters', {})

        if not query_text:
            return JsonResponse({
                "success": False,
                "error": "异文检索需要输入查询词"
            }, status=400)

        results = variant_search(query_text, filters)

        return JsonResponse({
            "success": True,
            "total": results['total'],
            "results": results['results']
        })
    except Exception as e:
        logger.error(f"异文检索出错: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)

# 提供高亮检索的专用API端点
@csrf_exempt
@require_http_methods(["POST"])
def api_highlight_search(request):
    """高亮检索专用API端点"""
    try:
        data = json.loads(request.body)
        query_text = data.get('query', '')
        filters = data.get('filters', {})

        results = highlight_search(query_text, filters)

        return JsonResponse({
            "success": True,
            "total": results['total'],
            "results": results['results']
        })
    except Exception as e:
        logger.error(f"高亮检索出错: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)

# 文档详情API端点
@csrf_exempt
@require_http_methods(["GET"])
def index_all(request):
    """重新创建索引并同步所有数据"""
    try:
        # 创建索引
        index_created = create_es_index()
        if not index_created:
            return JsonResponse({"success": False, "error": "索引创建失败"}, status=500)

        # 同步数据
        sync_success = sync_data()
        if not sync_success:
            return JsonResponse({"success": False, "error": "数据同步失败"}, status=500)

        # 获取文档计数
        es_stats = es.count(index=INDEX_NAME)
        es_count = es_stats["count"]

        conn = connect_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM documents")
            mysql_count = cursor.fetchone()[0]
        conn.close()

        return JsonResponse({
            "success": True,
            "message": "所有数据索引完成",
            "mysql_count": mysql_count,
            "es_count": es_count
        })
    except Exception as e:
        logger.error(f"索引所有数据失败: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def view_index_data(request):
    """查看索引中的数据"""
    try:
        size = request.GET.get('size', 10)
        from_pos = request.GET.get('from', 0)

        # 验证参数
        try:
            size = int(size)
            from_pos = int(from_pos)
            if size < 1 or size > 100:
                size = 10
            if from_pos < 0:
                from_pos = 0
        except ValueError:
            size = 10
            from_pos = 0

        query = {
            "query": {"match_all": {}},
            "from": from_pos,
            "size": size,
            "sort": [{"doc_id": {"order": "asc"}}]  # 按doc_id排序
        }

        results = es.search(index=INDEX_NAME, body=query)

        # 格式化返回数据
        documents = []
        for hit in results['hits']['hits']:
            doc = hit['_source']
            # 简化全文内容显示
            if 'full_text' in doc and len(doc['full_text']) > 100:
                doc['full_text'] = doc['full_text'][:100] + "..."
            documents.append(doc)

        return JsonResponse({
            "success": True,
            "total": results['hits']['total']['value'],
            "from": from_pos,
            "size": size,
            "documents": documents
        })
    except Exception as e:
        logger.error(f"查看索引数据失败: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)

# 添加一个直接同步指定文档的API
@csrf_exempt
@require_http_methods(["POST"])
def sync_single_document(request, doc_id):
    """同步单个文档到ES"""
    conn = None
    try:
        conn = connect_db()
        with conn.cursor() as cursor:
            # 获取文档基本信息
            cursor.execute("""
                SELECT doc_id, doc_title, doc_origin_id, doc_image, dynasty,
                       category_type, doc_specific_category, doc_style, doc_theme,
                       compilation_time, printing_time, publication_time, doc_type,
                       completeness, source
                FROM documents
                WHERE doc_id = %s
            """, (doc_id,))

            doc_info = cursor.fetchone()
            if not doc_info:
                return JsonResponse({"success": False, "error": "文档不存在"}, status=404)

            doc_id, doc_title, doc_origin_id, doc_image, dynasty, category_type, specific_category, doc_style, doc_theme, compile_time, printing_time, pub_time, doc_type, completeness, source = doc_info

            # 获取作者信息
            cursor.execute("""
                SELECT a.author_name
                FROM authors a
                JOIN document_author_links dal ON a.author_id = dal.author_id
                WHERE dal.doc_id = %s
            """, (doc_id,))

            author_rows = cursor.fetchall()
            author_names = ", ".join([row[0] for row in author_rows]) if author_rows else ""

            # 获取标题
            cursor.execute("""
                SELECT title_id, title_name, title_level
                FROM titles
                WHERE doc_id = %s
                ORDER BY title_order
            """, (doc_id,))

            titles = cursor.fetchall()
            title_name = titles[0][1] if titles else ""
            title_level = titles[0][2] if titles else ""

            # 获取全文内容
            full_text = ""
            cursor.execute("""
                SELECT ft.full_text
                FROM full_text_1 ft
                WHERE ft.title_id IN (
                    SELECT title_id FROM titles WHERE doc_id = %s
                )
            """, (doc_id,))

            full_text_rows = cursor.fetchall()
            full_text = " ".join([row[0] for row in full_text_rows if row[0]]) if full_text_rows else ""

            if not full_text:
                cursor.execute("""
                    SELECT ft.full_text
                    FROM full_text_1 ft
                    JOIN pages p ON ft.full_text_id = p.full_text_id_list
                    WHERE p.doc_id = %s
                """, (doc_id,))

                full_text_rows = cursor.fetchall()
                full_text = " ".join([row[0] for row in full_text_rows if row[0]]) if full_text_rows else ""

            # 获取页码信息
            cursor.execute("""
                SELECT page_number
                FROM pages
                WHERE doc_id = %s
                LIMIT 1
            """, (doc_id,))

            page_row = cursor.fetchone()
            page_number = page_row[0] if page_row else 0

            # 构建文档数据
            doc_data = {
                "doc_id": doc_id,
                "doc_title": doc_title if doc_title else "",
                "doc_origin_id": doc_origin_id if doc_origin_id else "",
                "doc_image": doc_image if doc_image else "",
                "dynasty": dynasty if dynasty else "",
                "category_type": category_type if category_type else "",
                "doc_specific_category": specific_category if specific_category else "",
                "doc_style": doc_style if doc_style else "",
                "doc_theme": doc_theme if doc_theme else "",
                "compilation_time": compile_time if compile_time else "",
                "printing_time": printing_time if printing_time else "",
                "publication_time": pub_time if pub_time else "",
                "doc_type": doc_type if doc_type else "",
                "completeness": completeness if completeness else "",
                "source": source if source else "",
                "title_name": title_name,
                "title_level": title_level,
                "full_text": full_text,
                "page_number": page_number,
                "author_name": author_names
            }

            # 索引到ES
            es.index(index=INDEX_NAME, id=doc_id, body=doc_data)
            es.indices.refresh(index=INDEX_NAME)

            return JsonResponse({
                "success": True,
                "message": f"文档 {doc_id} 已同步到ES",
                "document": {
                    "id": doc_id,
                    "title": doc_title,
                    "status": "synced"
                }
            })
    except Exception as e:
        logger.error(f"同步文档 {doc_id} 失败: {e}")
        return JsonResponse({
            "success": False,
            "error": str(e),
            "document_id": doc_id
        }, status=500)
    finally:
        if conn:
            conn.close()

# 初始化和同步数据的函数
@csrf_exempt
def init():
    """初始化Elasticsearch索引并同步数据"""
    try:
        # 检查索引是否存在，如果不存在则创建
        if not es.indices.exists(index=INDEX_NAME):
            create_es_index()
            sync_data()
        else:
            sync_incremental_data()
        logger.info("数据同步完成")
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        raise

@csrf_exempt
def initialize(request):
    if request.method == 'GET':
        init()
        return JsonResponse({"success": True, "message": "初始化完成"})
