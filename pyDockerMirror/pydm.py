import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import docker
import yaml

CONFIG_PATH = "/etc/pydm"
CONFIG_FILE = "/etc/pydm/config"

# 实例化docker客户端
client = docker.from_env()


def help_info():
    print(f"""
    PyDockerMirror, 软件版本1.1.0, 开发语言Python。\n
    用法：命令：pymd [option]
    
    init: 初始化配置文件，生成配置文件{CONFIG_FILE}，如再次使用将会覆盖原有信息。
    config: 打印配置信息。
    pull: 后边加镜像名。拉取镜像并修改Tag后，推送镜像至私有仓库中。
          镜像可以携带域名，携带域名时，请不要配置加速仓库。
    pull-local: 后边加镜像名。拉取镜像到本地，不会修改tag也不会推送至私有仓库。
    
    help: 打印此帮助信息。
    
    Tips：“pull”和“pull-local”命令，可以通过创建文件拉取多个镜像，文件内每个镜像需换行。
          如：
          registry.cn-shanghai.aliyuncs.com/pydm/centos7:latest
          registry.cn-shanghai.aliyuncs.com/pydm/ubuntu:latest
    """)


# 配置文件初始化
def init_config():
    domain = input("请输入私用仓库地址：")
    project = input("请输入私用仓库项目名称(默认为public)：")
    username = input("请输入私用仓库用户名：")
    password = input("请输入私用仓库密码：")
    if not project:
        project = "public"

    config = {
        "privateRegistry":
            {
                "domain": domain,
                "project": project,
                "username": username,
                "password": password,
            }
    }

    if not os.path.exists(CONFIG_PATH):
        os.mkdir(CONFIG_PATH, 755)
    with open(CONFIG_FILE, "w") as file:
        yaml.dump(config, file, default_flow_style=False, sort_keys=False)

    print(f"SUCCESS: 配置文件{CONFIG_FILE}已生成。")


# 查看配置文件
def open_config():
    with open(CONFIG_FILE, 'r') as outfile:
        yaml_config = yaml.safe_load(outfile)
        return yaml_config


# 拉取镜像
def pull_single(image):
    try:
        print(f"INFO: 开始拉取镜像{image}...")
        # cmd = subprocess.Popen(["docker", "pull", image], stdout=sys.stdout, stderr=sys.stderr)
        # stdout, stderr = cmd.communicate()
        # print(stdout)
        client.images.pull(image)
        print(f"SUCCESS: 镜像{image}拉取成功。")
        return image
    except IndexError as e:
        print(f"ERROR: 没有镜像名称。{e}")
    except Exception as e:
        print(f"Failed: 镜像拉取失败。{e}")


def pull_image():
    images = sys.argv[2]
    images_list = []
    pool = ThreadPoolExecutor(max_workers=10)
    # 判断是否为文件,也就是批量否？
    if os.path.isfile(images):
        with open(images, "rb") as f:
            images = f.readlines()
            for i in images:
                image = i.decode("utf-8").strip()
                pool.submit(pull_single, image)
                images_list.append(image)
        pool.shutdown()
        return images_list
    else:
        pool.submit(pull_single, images)
        images_list.append(images)
        pool.shutdown()
        return images_list


def rename_tag(images_list, registry, project):
    target_name_list = []
    for image in images_list:
        tag_name = image.split("/")[-1]
        target_name = f"{registry}/{project}/{tag_name}"
        subprocess.run(["docker", "tag", image, target_name], stdout=sys.stdout, stderr=sys.stderr)
        target_name_list.append(target_name)
        print(f"SUCCESS: 镜像{image}已被重新标记为{target_name}")
    return target_name_list


def push_image(target_name_list, username, password, domain, project):
    for target_name in target_name_list:
        try:
            print(f"正在推送镜像{target_name}至私有仓库: {domain}/{project}！")
            client.login(username=username, password=password, registry=domain)
            push_status = client.images.push(target_name)
            if "error" in push_status:
                print(f"推送信息：\n{push_status}")
                print(f"ERROR: 镜像{target_name}推送失败，请检查私有仓库地址或project是否正确！")
            else:
                print(f"SUCCESS: 镜像{target_name}推送成功！")
        except Exception as e:
            print(f"Failed: 镜像{target_name}推送失败, {e}")


if __name__ == '__main__':
    arguments = ["help", "init", "config", "pull", "pull-local"]
    arg_option = None
    if len(sys.argv) > 1:
        arg_option = sys.argv[1]
    if not arg_option or (arg_option not in arguments):
        print("ERROR: 无效参数，请使用命令'pydm help'查看帮助信息。")
    elif arg_option == "help":
        help_info()
    elif arg_option == "init":
        init_config()
    elif os.path.exists(CONFIG_FILE):
        config = open_config()
        domain = config.get("privateRegistry").get("domain")
        project = config.get("privateRegistry").get("project")
        username = config.get("privateRegistry").get("username")
        password = config.get("privateRegistry").get("password")
        if arg_option == "config":
            print(config)
        elif arg_option == "pull":
            images_list = pull_image()
            target_name_list = rename_tag(images_list, domain, project)
            push_image(target_name_list, username, password, domain, project)
            client.close()
        elif arg_option == "pull-local":
            images_list = pull_image()
            client.close()
    else:
        print("Warning: 未检测到pydm配置文件，请执行命令'pydm init'进行初始化！")
