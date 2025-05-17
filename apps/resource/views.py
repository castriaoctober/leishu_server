import os
import json
import pymysql
import re
import cn2an
from datetime import datetime
from django.http import JsonResponse
from django.views import View
from django.db import connection
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import logging

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class ResourceView(View):
    """
    通用资源处理视图，用于处理文献、编纂者、标题等资源的查询、插入和更新操作
    """
    def post(self, request):
        # 解析请求体
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
            # 根据不同的操作执行相应的函数
            if action == 'query':
                return self.execute_sql(data)
            else:
                # 根据请求的资源类型和操作类型执行相应的函数
                resource_type = self.get_resource_type(request.path)
                logger.info(f"资源类型: {resource_type}, 操作类型: {action}")
                
                if resource_type is None:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'不支持的资源类型: {request.path}'
                    }, status=400)
                
                if action == 'insert':
                    return self.insert_data(resource_type, data)
                elif action == 'update':
                    return self.update_data(resource_type, data)
                else:
                    return JsonResponse({'status': 'error', 'message': '不支持的操作'}, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': '无效的JSON格式'}, status=400)
        except Exception as e:
            logger.error(f"处理请求时发生错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    def get_resource_type(self, path):
        """根据请求路径确定资源类型"""
        logger.info(f"请求路径: {path}")
        
        if '/resource/document/' in path:
            return 'document'
        elif '/resource/author/' in path:
            return 'author'
        elif '/resource/document_author/' in path:
            return 'document_author'
        elif '/resource/title/' in path:
            return 'title'
        elif '/resource/fulltext/' in path:
            return 'fulltext'
        elif '/resource/page/' in path:
            return 'page'
        else:
            logger.error(f"未知的资源类型路径: {path}")
            return None
    
    def execute_sql(self, data):
        """执行SQL查询语句"""
        user_sql = data.get('sql')
        
        if not user_sql:
            return JsonResponse({'status': 'error', 'message': '缺少SQL查询语句'}, status=400)
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(user_sql)
                columns = [col[0] for col in cursor.description]
                result = [
                    dict(zip(columns, row))
                    for row in cursor.fetchall()
                ]
                
                # 处理结果中的日期和其他非序列化类型
                cleaned_result = []
                for row in result:
                    cleaned_row = {}
                    for key, value in row.items():
                        if value is None:
                            cleaned_row[key] = ""
                        else:
                            cleaned_row[key] = str(value)
                    cleaned_result.append(cleaned_row)
                
                return JsonResponse({'status': 'success', 'results': cleaned_result})
        except Exception as e:
            logger.error(f"SQL执行错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    def insert_data(self, resource_type, data):
        """插入数据"""
        try:
            logger.info("开始插入文献数据")
            logger.info(f"接收到的原始数据: {data}")
            
            # 根据资源类型确定表名和字段
            if resource_type == 'document':
                return self.insert_document_data(data)
            elif resource_type == 'author':
                return self.insert_author_data(data)
            elif resource_type == 'document_author':
                return self.insert_document_author_data(data)
            elif resource_type == 'title':
                return self.insert_title_data(data)
            elif resource_type == 'fulltext':
                return self.process_fulltext_data(data)
            else:
                return JsonResponse({'status': 'error', 'message': '不支持的资源类型'}, status=400)
        except Exception as e:
            logger.error(f"插入数据错误: {str(e)}")
            logger.error(f"错误类型: {type(e)}")
            logger.error(f"错误详情: {e.__dict__}")
            return JsonResponse({
                'status': 'error',
                'message': f'处理请求时发生错误: {str(e)}'
            }, status=500)
    
    def update_data(self, resource_type, data):
        """更新数据"""
        try:
            # 根据资源类型确定表名和字段
            if resource_type == 'document':
                return self.update_document_data(data)
            elif resource_type == 'author':
                return self.update_author_data(data)
            elif resource_type == 'document_author':
                return self.update_document_author_data(data)
            elif resource_type == 'title':
                return self.update_title_data(data)
            elif resource_type == 'page':
                return self.update_page_data(data)
            else:
                return JsonResponse({'status': 'error', 'message': '不支持的资源类型'}, status=400)
        except Exception as e:
            logger.error(f"更新数据错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    # 文献相关方法
    def insert_document_data(self, data):
        """插入文献数据"""
        try:
            logger.info("开始插入文献数据")
            logger.info(f"接收到的原始数据: {data}")
            
            # 移除action字段
            if 'action' in data:
                del data['action']
            
            # 数据验证和清理
            cleaned_data = {}
            for key, value in data.items():
                if value is None:
                    cleaned_data[key] = ''
                elif isinstance(value, str):
                    # 移除字符串两端的空白字符
                    cleaned_data[key] = value.strip()
                else:
                    cleaned_data[key] = str(value)
            
            logger.info(f"清理后的数据: {cleaned_data}")
            
            # 确保必填字段不为空
            required_fields = ['doc_title', 'doc_specific_category', 'doc_type']
            missing_fields = [field for field in required_fields if not cleaned_data.get(field)]
            if missing_fields:
                logger.error(f"缺少必填字段: {missing_fields}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'缺少必填字段: {", ".join(missing_fields)}'
                }, status=400)
            
            # 验证字段长度
            field_lengths = {
                'doc_title': 255,
                'doc_specific_category': 100,
                'doc_origin_id': 255,
                'doc_style': 50,
                'doc_type': 50,
                'doc_image': 255,
                'doc_theme': 255,
                'dynasty': 50,
                'compilation_time': 50,
                'printing_time': 50,
                'publication_time': 50,
                'completeness': 50,
                'source': 255
            }
            
            for field, max_length in field_lengths.items():
                if field in cleaned_data and len(cleaned_data[field]) > max_length:
                    logger.warning(f"字段 {field} 长度超过限制，将被截断")
                    cleaned_data[field] = cleaned_data[field][:max_length]
            
            # 构建SQL语句
            fields = list(cleaned_data.keys())
            placeholders = ", ".join(["%s"] * len(fields))
            columns = ", ".join(fields)
            values = [cleaned_data[k] for k in fields]
            
            sql = f"INSERT INTO documents ({columns}) VALUES ({placeholders})"
            
            logger.info(f"准备执行的SQL: {sql}")
            logger.info(f"SQL参数值: {values}")
            
            try:
                with connection.cursor() as cursor:
                    # 检查表结构
                    cursor.execute("DESCRIBE documents")
                    table_structure = cursor.fetchall()
                    logger.info(f"表结构: {table_structure}")
                    
                    # 执行插入
                    cursor.execute(sql, values)
                    inserted_id = cursor.lastrowid
                    logger.info(f"数据插入成功，ID: {inserted_id}")
                    
                    return JsonResponse({
                        'status': 'success',
                        'inserted_id': inserted_id,
                        'message': '文献数据插入成功'
                    })
            except Exception as db_error:
                logger.error(f"数据库操作错误: {str(db_error)}")
                logger.error(f"错误类型: {type(db_error)}")
                logger.error(f"错误详情: {db_error.__dict__}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'数据库操作错误: {str(db_error)}'
                }, status=500)
                
        except Exception as e:
            logger.error(f"插入文献数据时发生错误: {str(e)}")
            logger.error(f"错误类型: {type(e)}")
            logger.error(f"错误详情: {e.__dict__}")
            return JsonResponse({
                'status': 'error',
                'message': f'处理请求时发生错误: {str(e)}'
            }, status=500)
    
    def update_document_data(self, data):
        """更新文献数据"""
        doc_id = data.get('doc_id')
        if not doc_id:
            return JsonResponse({'status': 'error', 'message': '缺少doc_id'}, status=400)
        
        # 移除action字段和doc_id字段（后面会单独使用）
        if 'action' in data:
            del data['action']
        
        fields = [k for k in data if k != 'doc_id']
        set_clause = ", ".join([f"{k} = %s" for k in fields])
        values = [data[k] for k in fields] + [doc_id]
        
        sql = f"UPDATE documents SET {set_clause} WHERE doc_id = %s"
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                return JsonResponse({
                    'status': 'success',
                    'updated_rows': cursor.rowcount
                })
        except Exception as e:
            logger.error(f"更新文献数据错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    # 编纂者相关方法
    def insert_author_data(self, data):
        """插入编纂者数据"""
        # 移除action字段
        if 'action' in data:
            del data['action']
        
        fields = list(data.keys())
        placeholders = ", ".join(["%s"] * len(fields))
        columns = ", ".join(fields)
        values = [data[k] for k in fields]
        
        sql = f"INSERT INTO authors ({columns}) VALUES ({placeholders})"
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                return JsonResponse({
                    'status': 'success',
                    'inserted_id': cursor.lastrowid
                })
        except Exception as e:
            logger.error(f"插入编纂者数据错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    def update_author_data(self, data):
        """更新编纂者数据"""
        author_id = data.get('author_id')
        if not author_id:
            return JsonResponse({'status': 'error', 'message': '缺少author_id'}, status=400)
        
        # 移除action字段
        if 'action' in data:
            del data['action']
        
        fields = [k for k in data if k != 'author_id']
        set_clause = ", ".join([f"{k} = %s" for k in fields])
        values = [data[k] for k in fields] + [author_id]
        
        sql = f"UPDATE authors SET {set_clause} WHERE author_id = %s"
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                return JsonResponse({
                    'status': 'success',
                    'updated_rows': cursor.rowcount
                })
        except Exception as e:
            logger.error(f"更新编纂者数据错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    # 文献-编纂者关联相关方法
    def insert_document_author_data(self, data):
        """插入文献-编纂者关联数据"""
        # 移除action字段
        if 'action' in data:
            del data['action']
        
        fields = list(data.keys())
        placeholders = ", ".join(["%s"] * len(fields))
        columns = ", ".join(fields)
        values = [data[k] for k in fields]
        
        sql = f"INSERT INTO document_author_links ({columns}) VALUES ({placeholders})"
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                return JsonResponse({
                    'status': 'success',
                    'inserted_id': cursor.lastrowid
                })
        except Exception as e:
            logger.error(f"插入文献-编纂者关联数据错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    def update_document_author_data(self, data):
        """更新文献-编纂者关联数据"""
        da_id = data.get('da_id')
        if not da_id:
            return JsonResponse({'status': 'error', 'message': '缺少da_id'}, status=400)
        
        # 移除action字段
        if 'action' in data:
            del data['action']
        
        fields = [k for k in data if k != 'da_id']
        set_clause = ", ".join([f"{k} = %s" for k in fields])
        values = [data[k] for k in fields] + [da_id]
        
        sql = f"UPDATE document_author_links SET {set_clause} WHERE da_id = %s"
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                return JsonResponse({
                    'status': 'success',
                    'updated_rows': cursor.rowcount
                })
        except Exception as e:
            logger.error(f"更新文献-编纂者关联数据错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    # 标题相关方法
    def insert_title_data(self, data):
        """插入标题数据"""
        # 移除action字段
        if 'action' in data:
            del data['action']
        
        fields = list(data.keys())
        placeholders = ", ".join(["%s"] * len(fields))
        columns = ", ".join(fields)
        values = [data[k] for k in fields]
        
        sql = f"INSERT INTO titles ({columns}) VALUES ({placeholders})"
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                return JsonResponse({
                    'status': 'success',
                    'inserted_id': cursor.lastrowid
                })
        except Exception as e:
            logger.error(f"插入标题数据错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    def update_title_data(self, data):
        """更新标题数据"""
        title_id = data.get('title_id')
        if not title_id:
            return JsonResponse({'status': 'error', 'message': '缺少title_id'}, status=400)
        
        # 移除action字段
        if 'action' in data:
            del data['action']
        
        fields = [k for k in data if k != 'title_id']
        set_clause = ", ".join([f"{k} = %s" for k in fields])
        values = [data[k] for k in fields] + [title_id]
        
        sql = f"UPDATE titles SET {set_clause} WHERE title_id = %s"
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                return JsonResponse({
                    'status': 'success',
                    'updated_rows': cursor.rowcount
                })
        except Exception as e:
            logger.error(f"更新标题数据错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    # 页码相关方法
    def update_page_data(self, data):
        """更新页码数据"""
        page_id = data.get('page_id')
        if not page_id:
            return JsonResponse({'status': 'error', 'message': '缺少page_id'}, status=400)
        
        # 移除action字段
        if 'action' in data:
            del data['action']
        
        fields = [k for k in data if k != 'page_id']
        set_clause = ", ".join([f"{k} = %s" for k in fields])
        values = [data[k] for k in fields] + [page_id]
        
        sql = f"UPDATE pages SET {set_clause} WHERE page_id = %s"
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                return JsonResponse({
                    'status': 'success',
                    'updated_rows': cursor.rowcount
                })
        except Exception as e:
            logger.error(f"更新页码数据错误: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    # 全文处理相关方法
    def process_fulltext_data(self, data):
        """处理全文数据，包括插入引书、全文内容、更新关联关系和页码信息"""
        try:
            doc_id = data.get('doc_id')
            title_id = data.get('title_id')
            file_content = data.get('file_content')
            
            logger.info(f"接收到的数据: doc_id={doc_id}, title_id={title_id}, file_content长度={len(file_content) if file_content else 0}")
            logger.info(f"doc_id类型: {type(doc_id)}, title_id类型: {type(title_id)}")
            
            if not all([doc_id, title_id, file_content]):
                missing_fields = []
                if not doc_id: missing_fields.append('doc_id')
                if not title_id: missing_fields.append('title_id')
                if not file_content: missing_fields.append('file_content')
                
                logger.error(f"缺少必要参数: {', '.join(missing_fields)}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'缺少必要参数: {", ".join(missing_fields)}'
                }, status=400)
            
            # 将文件内容解析为JSON
            try:
                if isinstance(file_content, str):
                    logger.info("开始解析JSON字符串")
                    result = json.loads(file_content)
                    logger.info(f"JSON解析成功，数据条数: {len(result)}")
                    
                    # 验证数据格式
                    for item in result:
                        required_fields = ['text_type', 'full_text', 'full_text_order', 'title_level', 'title_id', 'doc_id']
                        missing_fields = [field for field in required_fields if field not in item]
                        if missing_fields:
                            logger.error(f"数据格式错误，缺少必要字段: {missing_fields}")
                            return JsonResponse({
                                'status': 'error',
                                'message': f'数据格式错误，缺少必要字段: {", ".join(missing_fields)}'
                            }, status=400)
                        
                        # 验证文本类型
                        if item['text_type'] not in ['引文', '引书', '注疏']:
                            logger.error(f"无效的文本类型: {item['text_type']}")
                            return JsonResponse({
                                'status': 'error',
                                'message': f'无效的文本类型: {item["text_type"]}'
                            }, status=400)
                        
                        # 验证标题级别
                        if not item['title_level'].startswith('h') or not item['title_level'][1:].isdigit():
                            logger.error(f"无效的标题级别: {item['title_level']}")
                            return JsonResponse({
                                'status': 'error',
                                'message': f'无效的标题级别: {item["title_level"]}'
                            }, status=400)
                    
                    logger.info(f"数据验证通过，第一条数据: {result[0]}")
                else:
                    logger.info("使用已解析的JSON对象")
                    result = file_content
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析错误: {str(e)}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'无效的JSON格式: {str(e)}'
                }, status=400)
            
            # 开始事务
            with connection.cursor() as cursor:
                try:
                    # 记录处理前的数据数量
                    cursor.execute("SELECT COUNT(*) FROM full_text_1")
                    before_fulltext_count = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM pages")
                    before_pages_count = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM documents")
                    before_docs_count = cursor.fetchone()[0]
                    
                    logger.info(f"处理前数据统计: full_text_1={before_fulltext_count}, pages={before_pages_count}, documents={before_docs_count}")
                    
                    # 步骤1: 处理并插入引书
                    logger.info("开始处理引书数据")
                    self.insert_documents_from_result(cursor, result, doc_id)
                    
                    # 步骤2: 插入全文内容
                    logger.info("开始插入全文内容")
                    self.insert_full_text(cursor, result)
                    
                    # 步骤3: 更新全文关联关系
                    logger.info("开始更新全文关联关系")
                    self.update_full_text_relationships(cursor, title_id)
                    
                    # 步骤4: 插入页码信息
                    logger.info("开始插入页码信息")
                    self.insert_pages(cursor, title_id)
                    
                    # 记录处理后的数据数量
                    cursor.execute("SELECT COUNT(*) FROM full_text_1")
                    after_fulltext_count = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM pages")
                    after_pages_count = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM documents")
                    after_docs_count = cursor.fetchone()[0]
                    
                    logger.info(f"处理后数据统计: full_text_1={after_fulltext_count}, pages={after_pages_count}, documents={after_docs_count}")
                    logger.info(f"数据变化: full_text_1={after_fulltext_count-before_fulltext_count}, pages={after_pages_count-before_pages_count}, documents={after_docs_count-before_docs_count}")
                    
                    # 验证插入的数据
                    cursor.execute("""
                        SELECT text_type, COUNT(*) as count 
                        FROM full_text_1 
                        WHERE title_id = %s 
                        GROUP BY text_type
                    """, (title_id,))
                    text_type_stats = cursor.fetchall()
                    logger.info(f"按文本类型统计: {text_type_stats}")
                    
                    cursor.execute("""
                        SELECT page_type, COUNT(*) as count 
                        FROM pages 
                        WHERE title_id = %s 
                        GROUP BY page_type
                    """, (title_id,))
                    page_type_stats = cursor.fetchall()
                    logger.info(f"按页面类型统计: {page_type_stats}")
                    
                    logger.info("所有处理步骤完成")
                    return JsonResponse({
                        'status': 'success',
                        'message': '全文数据处理完成',
                        'stats': {
                            'full_text_added': after_fulltext_count - before_fulltext_count,
                            'pages_added': after_pages_count - before_pages_count,
                            'documents_added': after_docs_count - before_docs_count,
                            'text_type_stats': text_type_stats,
                            'page_type_stats': page_type_stats
                        }
                    })
                except Exception as e:
                    logger.error(f"处理过程中发生错误: {str(e)}")
                    raise
        except Exception as e:
            logger.error(f"处理全文数据错误: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': f'处理全文数据错误: {str(e)}'
            }, status=500)
    
    def insert_documents_from_result(self, cursor, result, doc_id_to_add):
        """插入引书数据"""
        for item in result:
            if item.get("text_type") == "引书":
                # 整理书名
                book_title = item.get('full_text').strip()
                book_title_wrapped = f"《{book_title}》"
                
                # 使用 MATCH AGAINST 查询文献是否已存在
                cursor.execute(
                    """
                    SELECT doc_id, doc_origin_id FROM Documents
                    WHERE MATCH(doc_title) AGAINST (%s IN BOOLEAN MODE)
                    """,
                    (f'"{book_title}"',)
                )
                existing = cursor.fetchone()
                
                if existing:
                    this_doc_id = existing[0]
                    this_origin = existing[1]
                    
                    # 将 origin 处理为列表，检查是否已包含 doc_id_to_add
                    if this_origin and this_origin.strip():
                        origin_list = [x.strip() for x in this_origin.split(',') if x.strip()]
                        if str(doc_id_to_add) in origin_list:
                            logger.info(f"{book_title_wrapped} ➤ 已存在，origin_id 中已包含 {doc_id_to_add}")
                        else:
                            origin_list.append(str(doc_id_to_add))
                            new_origin = ','.join(origin_list)
                            cursor.execute(
                                """
                                UPDATE Documents
                                SET doc_origin_id = %s
                                WHERE doc_id = %s
                                """,
                                (new_origin, this_doc_id)
                            )
                            logger.info(f"{book_title_wrapped} ➤ 已存在，已将 {doc_id_to_add} 添加到 origin_id")
                    else:
                        # 如果 origin_id 是 None 或空字符串，则重新设置
                        cursor.execute(
                            """
                            UPDATE Documents
                            SET doc_origin_id = %s
                            WHERE doc_id = %s
                            """,
                            (str(doc_id_to_add), this_doc_id)
                        )
                        logger.info(f"{book_title_wrapped} ➤ 已存在，origin_id 设置为 {doc_id_to_add}")
                else:
                    # 插入新文献记录
                    cursor.execute(
                        """
                        INSERT INTO Documents (doc_title, doc_type, doc_origin_id)
                        VALUES (%s, %s, %s)
                        """,
                        (book_title_wrapped, False, str(doc_id_to_add))
                    )
                    logger.info(f"{book_title_wrapped} ➤ 新文献插入完成（origin_id={doc_id_to_add}）")
    
    def insert_full_text(self, cursor, result):
        """插入全文内容"""
        # 插入 SQL 语句
        insert_query = '''
        INSERT INTO full_text_1
        (full_text, full_text_order, title_level, title_id, text_type, related_id, quote_loc, doc_id, page_number, page_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        
        data_to_insert = []
        for entry in result:
            data_tuple = (
                entry.get('full_text'),
                entry.get('full_text_order'),
                entry.get('title_level'),
                entry.get('title_id'),
                entry.get('text_type'),
                entry.get('related_id', None),
                entry.get('quote_loc', None),
                entry.get('doc_id'),
                entry.get('page_number', None),
                entry.get('page_type', None)
            )
            data_to_insert.append(data_tuple)
        
        # 执行插入操作
        cursor.executemany(insert_query, data_to_insert)
        logger.info(f"{len(data_to_insert)} 条数据已成功插入 full_text_1 表。")
    
    def update_full_text_relationships(self, cursor, title_id):
        """更新全文关联关系"""
        # 查询 Full_Text_1 中该 title_id 的所有数据
        cursor.execute("""
            SELECT full_text_id, text_type
            FROM Full_Text_1
            WHERE title_id = %s
        """, (title_id,))
        rows = cursor.fetchall()
        logger.info(f"共获取数据 {len(rows)} 条")
        
        # 跟踪最后出现的 引书 和 引文 的 ID
        last_yinshu_id = None
        last_yinwen_id = None
        update_count = 0
        
        # 遍历数据并设置 related_id
        for row in rows:
            full_text_id = row[0]
            text_type = row[1]
            related_id = None
            
            if text_type == '引书':
                last_yinshu_id = full_text_id
                logger.info(f"发现引书 → ID {full_text_id}（related_id 不变）")
                continue
            
            elif text_type == '引文':
                if last_yinshu_id is not None:
                    related_id = last_yinshu_id
                    last_yinwen_id = full_text_id
                    logger.info(f"引文 → 关联到引书 ID {related_id}")
                else:
                    logger.warning(f"警告：没有引书情况下出现引文！ID {full_text_id}")
                    continue
            
            elif text_type == '注疏':
                if last_yinwen_id is not None:
                    related_id = last_yinwen_id
                    logger.info(f"注疏 → 关联到引文 ID {related_id}")
                else:
                    logger.warning(f"警告：没有引文情况下出现注疏！ID {full_text_id}")
                    continue
            
            if related_id is not None:
                cursor.execute("""
                    UPDATE Full_Text_1
                    SET related_id = %s
                    WHERE full_text_id = %s
                """, (related_id, full_text_id))
                update_count += 1
        
        logger.info(f"共更新 {update_count} 条 related_id 字段。")
    
    def insert_pages(self, cursor, title_id):
        """插入页码信息"""
        # 查询 full_text_1 中各页的 full_text_id 列表
        select_query = '''
        SELECT 
            doc_id,
            title_id,
            page_number,
            page_type,
            GROUP_CONCAT(full_text_id ORDER BY full_text_id ASC) AS full_text_id_list
        FROM 
            full_text_1
        WHERE
            title_id = %s
        GROUP BY
            doc_id, title_id, page_number, page_type
        ORDER BY
            doc_id ASC, title_id ASC, page_number ASC, page_type ASC;
        '''
        
        cursor.execute(select_query, (title_id,))
        rows = cursor.fetchall()
        
        # 构建插入 pages 表的数据
        pages_data = []
        
        for row in rows:
            pages_data.append((
                row[0],  # doc_id
                row[4],  # full_text_id_list
                row[2],  # page_number
                row[3],  # page_type
                None,    # page_image 暂无
                datetime.now(),  # create_time
                row[1]   # title_id
            ))
            
            logger.info(f"doc_id {row[0]}, page_number {row[2]}, page_type {row[3]}, title_id {row[1]}, 包含 full_text_id: {row[4]}")
        
        # 插入到 Pages 表中
        insert_query = '''
        INSERT INTO pages
        (doc_id, full_text_id_list, page_number, page_type, page_image, create_time, title_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''
        
        cursor.executemany(insert_query, pages_data)
        logger.info(f"{len(pages_data)} 条数据已插入 pages 表。") 