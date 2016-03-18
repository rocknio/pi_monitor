# -*- coding: utf-8 -*-
__author__ = 'Ryan'

import uuid
import os

class TempImage:
    def __init__(self, base_path="./", ext=".jpg"):
        # 创建文件夹路径
        self.path = "{base_path}/capture/{rand}{ext}".format(base_path=base_path, rand=str(uuid.uuid4()), ext=ext)

    def cleanup(self):
        # 删除文件
        os.remove(self.path)
