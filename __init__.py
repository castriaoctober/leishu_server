# 告诉Django使用pymysql作为MySQL的驱动
import pymysql
# 为实现版本兼容，可以指定mysqlclient的版本，例如
# pymysql.version_info = (1, 3, 13, 'final', 0)
pymysql.install_as_MySQLdb()