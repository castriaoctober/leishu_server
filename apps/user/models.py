from django.db import models
from django.db.models import TextChoices
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager

from ..read.models import Page, Doc, FullText1

class LogAction(TextChoices):
    INSERT = 'insert', '插入'
    DELETE = 'delete', '删除'
    UPDATE = 'update', '更新'

# ---------------------- 自定义用户模型 ----------------------
class UserManager(BaseUserManager):
    def create_user(self, email=None, password=None, **extra_fields):
        if not email:
            raise ValueError('必须提供邮箱')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password):
        user = self.create_user(email, password)
        user.is_admin = True
        user.save(using=self._db)
        return user

class User(AbstractBaseUser):
    user_id = models.AutoField(primary_key=True)
    user_name = models.CharField('用户名', max_length=50, unique=True)
    email = models.EmailField('邮箱', max_length=100, unique=True)
    password = models.CharField('密码', max_length=128)  # 加密后长度固定为128
    is_admin = models.BooleanField('管理员', default=False)
    is_active = models.BooleanField('是否激活', default=True)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    last_log_in_time = models.DateTimeField('最后登录', null=True, auto_now=True)
    last_login = None  # 为了兼容django.contrib.auth.models.AbstractBaseUser

    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['user_name']

    class Meta:
        db_table = 'users'
        verbose_name = '用户'
        verbose_name_plural = '用户'

    def __str__(self):
        # return str(self.__dict__())
        return dict(user_id=self.user_id, user_name=self.user_name,
            email=self.email, is_admin=self.is_admin,
            create_time=self.create_time, last_log_in_time=self.last_log_in_time
            )


# ---------------------- 用户行为模型 ----------------------
class CollectedDoc(models.Model):
    collect_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    doc = models.ForeignKey(Doc, on_delete=models.CASCADE, db_column='doc_id')
    create_time = models.DateTimeField('收藏时间', auto_now_add=True)
    tag = models.CharField('标签', max_length=200, blank=True)

    class Meta:
        db_table = 'collected_documents'
        verbose_name = '收藏文献'

    def to_dict(self):
        res = {}
        for field in self._meta.fields:
            res[field.name] = getattr(self, field.name)
        # 处理外键字段
        docs = Doc.objects.get(doc_id=self.doc).to_dict()
        res['doc_title'] = docs.doc_title
        # res['doc_authors'] = docs.doc_authors
        return res

class Bookmark(models.Model):
    mark_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, default=None, on_delete=models.CASCADE, db_column='user_id')
    doc = models.ForeignKey(Doc, default=None, on_delete=models.CASCADE, db_column='doc_id')
    page = models.ForeignKey(Page, on_delete=models.CASCADE, db_column='page_id')
    note = models.TextField('备注', blank=True)
    selection_data = models.TextField(null=True,blank=True,default=None)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    tag = models.CharField('标签', max_length=200, blank=True)

    class Meta:
        db_table = 'bookmarks'
        verbose_name = '书签'

class HistoryRecord(models.Model):
    history_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, default=None, on_delete=models.CASCADE, db_column='user_id')
    doc = models.ForeignKey(Doc, default=None, on_delete=models.CASCADE, db_column='doc_id')
    browse_time = models.DateTimeField('浏览时间', auto_now_add=True)

    class Meta:
        db_table = 'historyrecords'
        verbose_name = '历史记录'

# ---------------------- 系统表 ----------------------
class LeishuStopword(models.Model):
    value = models.CharField('停用词', max_length=30, unique=True)

    class Meta:
        db_table = 'leishu_stopwords'
        verbose_name = '停用词表'

class Log(models.Model):
    log_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column='user_id')
    log_action = models.CharField('操作类型', max_length=10, choices=LogAction.choices)
    log_time = models.DateTimeField('操作时间', auto_now_add=True)
    log_affected = models.CharField('影响对象', max_length=50)
    log_mark = models.CharField('备注', max_length=200, blank=True)

    class Meta:
        db_table = 'logs'
        verbose_name = '操作日志'