from django.db import models
from django.db.models import TextChoices
from time import timezone

# --------------- 枚举类型定义（Django 3.0+ 支持） ---------------
# (实际/数据库存储值, 字面/表单显示值)

class RoleType(TextChoices):
    AUTHOR = '著', '著'
    TRANSLATOR = '译', '译'
    PROOFREADER = '校', '校'
    # ...其他角色类型

class TitleLevel(TextChoices):
    DOCUMENT = 'document', 'Document'
    H1 = 'h1', 'H1'
    H2 = 'h2', 'H2'
    H3 = 'h3', 'H3'
    H4 = 'h4', 'H4'

# ---------------------- 枚举类型定义 ----------------------
class SpecificCategory(models.TextChoices):
    BIOGRAPHY = '传记', '传记'
    NAME_BOOK = '姓名书', '姓名书'
    GENEALOGY = '谱牒', '谱牒'
    RHYME_BOOK = '韵书', '韵书'
    COMPREHENSIVE = '综合性类书', '综合性类书'
    SPECIALIZED = '专书性类书', '专书性类书'

class DocStyle(models.TextChoices):
    EVENT = '类事', '类事'
    TEXT = '类文', '类文'
    INTEGRATED = '事文一体', '事文一体'

class TextType(models.TextChoices):
    MAIN = '正文', '正文'
    QUOTE = '引文', '引文'
    ANNOTATION = '注疏', '注疏'
    REFERENCE = '引书', '引书'

class PageType(models.TextChoices):
    A = 'A', '右页'
    B = 'B', '左页'

class LogAction(models.TextChoices):
    INSERT = 'insert', '插入'
    DELETE = 'delete', '删除'
    UPDATE = 'update', '更新'


# ---------------------- 核心模型 ----------------------
class Doc(models.Model):
    doc_id = models.AutoField(primary_key=True)
    doc_title = models.CharField('文献标题', max_length=100)
    category_type = models.BooleanField('分类类型', default=True) 
    doc_specific_category = models.CharField('具体分类', max_length=10, choices=SpecificCategory.choices)
    doc_style = models.CharField('文献类型', max_length=10, choices=DocStyle.choices)
    compilation_time = models.CharField('编纂时间', max_length=100)
    printing_time = models.CharField('印刷时间', max_length=100)
    publication_time = models.CharField('出版时间', max_length=100)
    doc_type = models.BooleanField('文献类型标记', default=True)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    dynasty = models.CharField(
        '朝代',
        max_length=10,
        choices=[
            ('先秦', '先秦'), ('秦', '秦'), ('汉', '汉'),
            ('三国', '三国'), ('晋', '晋'), ('南北朝', '南北朝'),
            ('隋', '隋'), ('唐', '唐'), ('五代十国', '五代十国'),
            ('宋', '宋'), ('元', '元'), ('明', '明'),
            ('清', '清'), ('民国', '民国'), 
            ('近现代', '近现代'), ('当代', '当代')
        ],
        blank=True,
        null=True)
    compilation_time = models.CharField(max_length=100, null=True, blank=True, verbose_name='编纂时间')
    printing_time = models.CharField(max_length=100, null=True, blank=True, verbose_name='印刷时间')
    publication_time = models.CharField(max_length=100, null=True, blank=True, verbose_name='出版时间')
    source = models.CharField('元数据来源',max_length=100)
    doc_origin_id = models.TextField(blank=True, null=True)
    doc_image = models.TextField('书籍封面图片路径', blank=True, null=True)

    class Meta:
        db_table = 'documents'
        verbose_name = '文献'
        indexes = [
            models.Index(fields=['doc_title'], name='doc_title_idx'),
        ]

class Author(models.Model):
    author_id = models.AutoField(primary_key=True)
    author_name = models.CharField('姓名', max_length=100)
    author_org = models.CharField('机构', max_length=100, blank=True)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'authors'
        verbose_name = '编纂者'
        indexes = [
            models.Index(fields=['author_name'], name='author_name_idx'),
            models.Index(fields=['author_org'], name='author_org_idx'),
        ]

class DALink(models.Model):
    da_id = models.AutoField(primary_key=True)
    doc_id = models.ForeignKey(Doc, on_delete=models.CASCADE, db_column='doc_id')
    author_id = models.ForeignKey(Author, on_delete=models.CASCADE, db_column='author_id')
    role = models.CharField('角色', max_length=10)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'document_author_links'
        verbose_name = '文献-编纂者关联'

class Title(models.Model):
    title_id = models.AutoField(primary_key=True)
    title_name = models.CharField('标题名称', max_length=100)
    title_level = models.CharField('标题层级', max_length=8, null=True, default=None, blank=True, choices=TitleLevel.choices)
    parent_id = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, db_column='parent_id')
    title_order = models.PositiveIntegerField('排序')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    doc = models.ForeignKey(
        'Doc',  
        on_delete=models.CASCADE,
        db_column='doc_id'  
    )

    class Meta:
        db_table = 'titles'
        verbose_name = '标题'
        indexes = [
            models.Index(fields=['title_name'], name='title_name_idx'),
        ]

class FullText1(models.Model):
    full_text_id = models.AutoField(primary_key=True)
    full_text = models.TextField('全文内容')
    full_text_order = models.PositiveIntegerField('段落顺序')
    title_id = models.ForeignKey(Title, on_delete=models.SET_NULL, null=True, db_column='title_id')
    title_level = models.CharField('标题层级', max_length=8, null=True, default=None, blank=True, choices=TitleLevel.choices)
    text_type = models.CharField('文本类型', max_length=10, choices=TextType.choices)
    related_id = models.PositiveIntegerField('关联ID', null=True)
    quote_loc = models.PositiveSmallIntegerField('引用位置', null=True)
    doc_id = models.ForeignKey(Doc, on_delete=models.CASCADE, db_column='doc_id')
    page_number = models.PositiveSmallIntegerField('页码', default=0)
    page_type = models.CharField('页面类型', max_length=1, choices=PageType.choices, null=True)

    class Meta:
        db_table = 'full_text_1'
        verbose_name = '全文段落'
        indexes = [
            models.Index(fields=['full_text'], name='full_text_idx'),
        ]

class Page(models.Model):
    page_id = models.AutoField(primary_key=True)
    doc_id = models.ForeignKey(Doc, on_delete=models.CASCADE, db_column='doc_id')
    full_text_id_list = models.TextField('全文段落列表', blank=True)
    page_number = models.PositiveIntegerField('页码')
    page_type = models.CharField('页面类型', max_length=1, choices=PageType.choices)
    page_image = models.TextField('页面图像路径', blank=True)
    title_id = models.ForeignKey(Title, on_delete=models.SET_NULL, null=True, db_column='title_id')
    create_time = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'pages'
        verbose_name = '页码信息'
