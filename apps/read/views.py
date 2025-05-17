from django.http import JsonResponse
from django.views import View
from .models import Doc, Title, FullText1, Page, Author, DALink
from django.db.models import Count, Q
import json
from django.shortcuts import get_object_or_404
import re
from django.conf import settings


class DocListView(View):
    def get(self, request):
        # 获取查询参数
        dynasty = request.GET.get('dynasty')
        category_type = request.GET.get('category_type')
        doc_specific_category = request.GET.get('doc_specific_category')
        doc_style = request.GET.get('doc_style')
        
        # 构建查询条件
        filters = {}
        if dynasty:
            filters['dynasty'] = dynasty
        if category_type:
            filters['category_type'] = category_type
        if doc_specific_category:
            filters['doc_specific_category'] = doc_specific_category
        if doc_style:
            filters['doc_style'] = doc_style
        
        # 获取书籍数据
        books = Doc.objects.filter(**filters)
        
        # 分离doc_type为True和False的书籍
        main_books = books.filter(doc_type=True).values('doc_id', 'doc_title', 'dynasty')
        supplement_books = books.filter(doc_type=False).values('doc_id', 'doc_title', 'dynasty')
        
        return JsonResponse({
            'main_books': list(main_books),
            'supplement_books': list(supplement_books)
        })

class DynastyStatsView(View):
    def get(self, request):
        # 统计各朝代的书籍数量，排除dynasty为null或空字符串的记录
        stats = Doc.objects.exclude(dynasty__isnull=True).exclude(dynasty='').values('dynasty').annotate(count=Count('doc_id')).order_by('dynasty')
        return JsonResponse(list(stats), safe=False)

class CategoryTreeView(View):
    def get(self, request):
        # 构建分类树
        category_tree = [
            {
                'name': '广义类书',
                'value': 'true',
                'children': [
                    {'name': '传记', 'value': '传记'},
                    {'name': '谱牒', 'value': '谱牒'},
                    {'name': '姓名书', 'value': '姓名书'},
                    {'name': '韵书', 'value': '韵书'},
                ]
            },
            {
                'name': '狭义类书',
                'value': 'false',
                'children': [
                    {
                        'name': '综合性类书',
                        'value': '综合性类书',
                        'children': [
                            {'name': '综合性类事类书', 'value': '类事'},
                            {'name': '综合性类文类书', 'value': '类文'},
                            {'name': '综合性事文一体类书', 'value': '事文一体'},
                        ]
                    },
                    {
                        'name': '专书性类书',
                        'value': '专书性类书',
                        'children': [
                            {'name': '专书性类事类书', 'value': '类事'},
                            {'name': '专书性类文类书', 'value': '类文'},
                            {'name': '专书性类事类文类书', 'value': '事文一体'},
                        ]
                    },
                    {
                        'name': '主题内容',
                        'value': '主题内容',
                        'children': [
                            {'name': '天', 'value': '天'},
                            {'name': '地', 'value': '地'},
                            {'name': '人', 'value': '人'},
                            {'name': '事', 'value': '事'},
                            {'name': '物', 'value': '物'},
                        ]
                    }
                ]
            }
        ]
        return JsonResponse(category_tree, safe=False)

class DocDetailView(View):
    def get(self, request, doc_id):
        try:
            doc = Doc.objects.get(doc_id=doc_id)
            # 获取关联的编纂者信息
            da_links = DALink.objects.filter(doc_id=doc_id).select_related('author_id')
            authors = [{
                'author_id': link.author_id.author_id,
                'author_name': link.author_id.author_name,
                'author_org': link.author_id.author_org,
                'role': link.role
            } for link in da_links]
            
            data = {
                'doc_id': doc.doc_id,
                'doc_title': doc.doc_title,
                'dynasty': doc.dynasty,
                'category_type': doc.category_type,
                'doc_specific_category': doc.doc_specific_category,
                'doc_style': doc.doc_style,
                'compilation_time': doc.compilation_time,
                'printing_time': doc.printing_time,
                'publication_time': doc.publication_time,
                'doc_type': doc.doc_type,
                'authors': authors,
                'doc_image':doc.doc_image,
            }
            return JsonResponse(data)
        except Doc.DoesNotExist:
            return JsonResponse({'error': 'Document not found'}, status=404)

class AuthorDetailView(View):
    def get(self, request, author_id):
        try:
            author = Author.objects.get(author_id=author_id)
            # 获取编纂者参与的文献
            da_links = DALink.objects.filter(author_id=author_id).select_related('doc_id')
            documents = [{
                'doc_id': link.doc_id.doc_id,
                'doc_title': link.doc_id.doc_title,
                'role': link.role
            } for link in da_links]
            
            data = {
                'author_id': author.author_id,
                'author_name': author.author_name,
                'author_org': author.author_org,
                'create_time': author.create_time.strftime('%Y-%m-%d %H:%M:%S'),
                'documents': documents  # 编纂者参与的文献列表
            }
            return JsonResponse(data)
        except Author.DoesNotExist:
            return JsonResponse({'error': 'Author not found'}, status=404)
        

# 修正后的标题树构造函数
def build_tree(titles, parent_id=None):
    tree = []
    # 获取当前层级标题，并按照 title_order 排序
    current_level_titles = sorted([t for t in titles if t.parent_id_id == parent_id], key=lambda x: x.title_order)

    for title in current_level_titles:
        children = build_tree(titles, title.title_id)
        tree.append({
            "title_id": title.title_id,
            "title_name": title.title_name,
            "title_level": title.title_level,
            "children": children,
        })
    return tree

class TitleTreeView(View):
    def get(self, request, doc_id):
        titles = list(Title.objects.filter(doc_id=doc_id))  # 转换为列表，确保排序生效
        tree = build_tree(titles, parent_id=None)
        doc = Doc.objects.get(doc_id=doc_id)
        doc_title = doc.doc_title
        
        # 构造返回数据，包含标题树和文档标题
        response_data = {
            "doc_title": doc_title,
            "tree": tree,
        }
        
        return JsonResponse(response_data, safe=False)



# 获取书籍的页码和内容
class PageContentView(View):
    def get(self, request, doc_id):
        pages = Page.objects.filter(doc_id=doc_id).order_by("page_number", "page_type")
        page_data = []

        for page in pages:
            full_text_ids = page.full_text_id_list.split(',')
            full_texts = FullText1.objects.filter(full_text_id__in=full_text_ids).order_by("full_text_order")

            page_data.append({
                "page_number": page.page_number,
                "page_type": page.page_type,
                "title_id": page.title_id_id if page.title_id else None, 
                "full_texts": [{"text": text.full_text, "text_type": text.text_type,"text_id":text.full_text_id,"related_id":text.related_id} for text in full_texts],
                "page_image": request.build_absolute_uri(settings.MEDIA_URL + page.page_image) if page.page_image else None,              
                "page_id":page.page_id,
            })

        return JsonResponse(page_data, safe=False)


class TitleTextsView(View):
    def get(self, request, doc_id, title_id):
        texts = FullText1.objects.filter(doc_id=doc_id, title_id=title_id).order_by("full_text_order")
        data = [{"full_text": text.full_text, "text_type": text.text_type} for text in texts]
        return JsonResponse(data, safe=False)
    

def supplement_book_info(request, doc_id):
    try:
        # Get the supplement book
        book = Doc.objects.get(doc_id=doc_id, doc_type=False)
        
        # Extract Chinese title by removing 《 and 》
        chinese_title = re.sub(r'[《》]', '', book.doc_title)
        
        # Find matching full text records
        matching_records = FullText1.objects.filter(
            Q(full_text=chinese_title) | 
            Q(full_text__startswith=chinese_title) |
            Q(full_text__contains=chinese_title)
        )
        
        # Get all content records where related_id matches the matching_records' full_text_id
        content_records = []
        for record in matching_records:
            contents = FullText1.objects.filter(
                related_id=record.full_text_id
            ).order_by('full_text_order')
            content_records.extend(contents)
        
        # Prepare response data
        response_data = {
            'book': {
                'doc_id': book.doc_id,
                'doc_title': book.doc_title,
                'dynasty': book.dynasty,
                'doc_specific_category': book.doc_specific_category,
                'doc_style': book.doc_style,
                'compilation_time': book.compilation_time,
                'printing_time': book.printing_time,
                'publication_time': book.publication_time,
                'source': book.source,
            },
            'contents': [
                {
                    'full_text_id': r.full_text_id,
                    'full_text': r.full_text,
                    'full_text_order': r.full_text_order,
                    'text_type': r.text_type,
                    'page_number': r.page_number,
                    'page_type': r.page_type,
                } for r in content_records
            ]
        }
        
        return JsonResponse(response_data)
    
    except Doc.DoesNotExist:
        return JsonResponse({'error': 'Supplement book not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
def get_reconstructed_texts(request, doc_id):
    try:
        # (1) 获取当前文献标题并处理
        current_doc = Doc.objects.get(doc_id=doc_id)
        original_title = current_doc.doc_title.strip('《》')  # 去掉书名号
        
        # 查找full_text与书名相同的记录
        matching_texts = FullText1.objects.filter(
            full_text=original_title
        ).select_related('doc_id')
        
        results = []
        for text in matching_texts:
            # (2) 获取related_id对应的内容并按顺序组织
            related_contents = FullText1.objects.filter(
                related_id=text.full_text_id
            ).order_by('full_text_order')
            
            content_list = [{
                'text': item.full_text,
                'order': item.full_text_order,
                'text_type': item.text_type,
                'page_number':item.page_number,
                'page_type':item.page_type,
            } for item in related_contents]
            
            # (3) 组织返回数据
            results.append({
                'source_doc_id': text.doc_id.doc_id,
                'source_doc_title': text.doc_id.doc_title,
                'full_text_id': text.full_text_id,
                'contents': content_list
            })
        
        return JsonResponse({
            'status': 'success',
            'original_title': original_title,
            'reconstructions': results,
        })
    
    except Doc.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '文献不存在'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    


# 引书信息
def get_book_origins(request, doc_id):
    """
    获取引书的来源类书信息
    :param doc_id: 当前引书ID
    """
    try:
        book = Doc.objects.get(doc_id=doc_id, doc_type=False)  # 确保是引书
        
        origin_books = []
        if book.doc_origin_id:
            try:
                # 处理doc_origin_id字符串，可能是"1,2,3"或"1"等形式
                origin_ids = [int(id_str.strip()) for id_str in book.doc_origin_id.split(',') if id_str.strip()]
                
                # 获取所有来源类书信息
                origin_books = Doc.objects.filter(
                    doc_id__in=origin_ids,
                    doc_type=True  # 只查询类书
                ).values('doc_id', 'doc_title').order_by('doc_title')
                
                origin_books = list(origin_books)
            except (ValueError, AttributeError) as e:
                print(f"解析doc_origin_id出错: {e}")
        
        return JsonResponse({
            'status': 'success',
            'data': {
                'origin_books': origin_books,
                'current_doc_id': doc_id
            }
        })
    
    except Doc.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '引书不存在'}, status=404)

def get_related_books(request):
    """
    获取同源引书
    :param current_doc_id: 当前引书ID (用于排除自身)
    :param origin_id: 来源类书ID
    """
    current_doc_id = request.GET.get('current_doc_id')
    origin_id = request.GET.get('origin_id')
    
    if not current_doc_id or not origin_id:
        return JsonResponse({'status': 'error', 'message': '参数缺失'}, status=400)
    
    try:
        # 查找所有doc_origin_id包含该origin_id的引书(排除自身)
        related_books = Doc.objects.filter(
            Q(doc_origin_id__contains=f",{origin_id},") |
            Q(doc_origin_id__startswith=f"{origin_id},") |
            Q(doc_origin_id__endswith=f",{origin_id}") |
            Q(doc_origin_id=f"{origin_id}"),
            doc_type=False  # 只查询引书
        ).exclude(doc_id=current_doc_id).values('doc_id', 'doc_title').order_by('doc_title')
        
        return JsonResponse({
            'status': 'success',
            'data': list(related_books)
        })
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)