import pymysql

# Django's MySQL backend expects the `MySQLdb` driver (mysqlclient), which
# needs C++ build tools to compile on Windows. PyMySQL is a pure-Python
# equivalent, and this line makes it pretend to be MySQLdb so Django is
# happy without any compiler needed.
pymysql.install_as_MySQLdb()
