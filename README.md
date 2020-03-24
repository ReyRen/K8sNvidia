# K8sNvidia
使用k8s对GPU集群进行管理

## 心路历程
如何将办公室中的GPU充分的利用与集中管理起来， 一开始也会想到openStack之类的虚拟化技术， 然后将节点组成集群，驱动穿透. 但是这样的操作成本预计资源耗费成本过于庞大. 我心之中发现了Nvidia-docker,也见识了K8s进行管理的强大之处. 索性将Nvidia-docker交由K8s进行管理。此种想法已在两年前就有了，网上的资料原理大致相同，但是由于版本过于陈旧或者叙述不够详尽等问题，着实让我在坑中挣扎很久. 所以， 这不是创新，而是一些解决方案的记录，错误的解决历程，宏观层面一些东西的原理性解释.  以此送给健忘的我. 

## 当前环境
| Hostname        |IP    | GPU数量   | 操作系统 | 内核版本 | 
| --------   | -----:   | :----: | :----: | :----: |
| cluster-msater        | 192.168.0.113     |   0    | CentOS Linux release 7.7.1908 (Core) | 3.10.0-1062.18.1.el7.x86_64 |
| node-110        | 192.168.0.110      |   1*1080Ti    | CentOS Linux release 7.7.1908 (Core) | 3.10.0-1062.18.1.el7.x86_64 |
| noed-109        | 192.168.0.109      |   1*1080Ti    | CentOS Linux release 7.7.1908 (Core) | 3.10.0-1062.18.1.el7.x86_64 |
| noed-106        | 192.168.0.106      |   1*1080Ti    | CentOS Linux release 7.7.1908 (Core) | 3.10.0-1062.18.1.el7.x86_64 |
| node-105        | 912.168.0.105      |   1*1080Ti    | Ubuntu 18.04.3 LTS | 5.3.0-40.x86_64 |


## 规划
cluster-master作为k8s的master节点不参与训练，只是用来分配pod

node-110 node-109 node-106用来作为pod迁移节点

至于node-105, 因为是Ubuntu系统，想让它作为新的节点进行加入操作，看看可行性

(PS. 系统发行版不一样不知道会不会受影响，但是内核版本不一样是肯定会受影响的，所以我打算将所以内核先统一到5.3.0)

(PPS. 按照现实安全环境考虑，所有操作非声明， 则为非root操作，但是是有sudoer权限的)

## 运行环境准备
### cluster-master:
首先我们进行内核的升级.升级到和各个节点同样的内核版本

首先先导入elrepo的key:
```
sudo rpm --import https://www.elrepo.org/RPM-GPG-KEY-elrepo.org
```
然后安装yum源:
```
sudo rpm -Uvh http://www.elrepo.org/elrepo-release-7.0-2.el7.elrepo.noarch.rpm
```
启用仓库后，可以使用下面的命令查看可以使用的内核相关的包:
```
sudo yum --disablerepo="*" --enablerepo="elrepo-kernel" list available
```
我看到有ml版本(5.5.11-1.el7), 淡定. ml版本可能存在Nvidia官方驱动还不支持的情况哦
可以参考一下[forums的讨论](https://forums.developer.nvidia.com/t/installation-fails-with-kernels-5-1-x/77489):
所以我还是选择了lt长期维护版， 这里是4.4.217-1.el7
```
sudo yum -y --enablerepo=elrepo-kernel install kernel-lt.x86_64 kernel-lt-devel.x86_64
```
这时候，在/etc/grub2.cfg中搜索"menuentry"能看到4.4.217的内核是在启动位置0的. 如果想哟生效，我们需要更改内核的启动顺序
```
sudo vim /etc/default/grub
# 将GRUB_DEFAULT=saved 改为GRUB_DEFAULT=0
```
重新创建一下内核配置
```
sudo grub2-mkconfig -o /boot/grub2/grub.cfg
sudo reboot
```

### node-:
很多人在安装完驱动程序后，才想到内核需要进行升级，那么，这次我也这样作死一波，如果是无驱动前提下升级内核，那就升级内核和驱动安装调换顺序就行
前往[Nvidia Driver](https://www.geforce.cn/drivers)进行选择官方驱动
```
cd ~
wget http://cn.download.nvidia.com/XFree86/Linux-x86_64/440.64/NVIDIA-Linux-x86_64-440.64.run
```
接下来需要安装依赖
```
sudo yum update
sudo yum -y install gcc dkms
```
阻止nouveau模块儿加载, nouveau是操作系统自带的显卡驱动，这里我们需要Nvidia专用显卡驱动. 
我曾经Nvidia没装成功并且还将nouveau关闭掉，作死的换了个高清壁纸，图形化界面直接卡死，幸好终端模式不受影响
```
# 查看是否有加载nouveau驱动模块儿，有输出就需要将他屏蔽
lsmod | grep nouveau

# 使用root
echo -e "blacklist nouveau\noptions nouveau modeset=0" > /etc/modprobe.d/blacklist.conf
```
重新构建一下initramfs image文件
至于什么是initramfs, 通俗的来说就是内核在启动的时候会将会从这个image中的文件导入到rootfs中，然后内核检查rootfs中是否有init文件，如果有则执行它并且作为1号进程. 这个1号进程也就接管了后续的工作, 包括定位挂在真正的文件系统等. 如果没有在rootfs中找到init文件，那么内核会按照以前的版本定位方式挂载跟分区.这里我们更改了内核模块儿，最好的方式就是备份之前的initramfs， 然后重新生成一份
```
# 使用root
sudo mv /boot/initramfs-$(uname -r).img /boot/initramfs-$(uname -r).img.bak
dracut /boot/initramfs-$(uname -r).img $(uname -r)
reboot
```
运行驱动安装程序(如果你在图形化界面操作，那你得执行init 3进行非X server环境下， 不然安装过程中会报错的)
```
chmod +x NVIDIA-Linux-x86_64-440.36.run
sudo ./NVIDIA-Linux-x86_64-440.36.run
```
如果在这个时候报错了：Unable to find the kernel source tree for the currently running kernel
说明现在没有制定版本的kernel-devel包， 也就是说/usr/src/kernels/目录下是没有当前内核版本的kernel-tree的
```
# 查看目前内核版本
uname -a
# 查看一下目前的源中有的可下载的kernel-devel版本
yum list | grep kernel-devel
# 如果发现一致，那么直接sudo yum install kernel-devel就行了
# 如果发现不一致, 那么可以去[koji](https://koji.fedoraproject.org/koji)或者[kernel-devel](https://pkgs.org/download/kernel-devel) 
```
这样你就会在/usr/src/kernel/下看到对应tree了. 
按照提示就会将驱动安装完成， 最后记得reboot一下

驱动安装完成后
```
nvidia-smi
```
可以看到显示的效果
接下来我们进行内核的升级.
首先先导入elrepo的key:
```
sudo rpm --import https://www.elrepo.org/RPM-GPG-KEY-elrepo.org
```
然后安装yum源:
```
sudo rpm -Uvh http://www.elrepo.org/elrepo-release-7.0-2.el7.elrepo.noarch.rpm
```
启用仓库后，可以使用下面的命令查看可以使用的内核相关的包:
```
sudo yum --disablerepo="*" --enablerepo="elrepo-kernel" list available
```
我看到有ml版本(5.5.11-1.el7), 淡定. ml版本可能存在Nvidia官方驱动还不支持的情况哦
可以参考一下[forums的讨论](https://forums.developer.nvidia.com/t/installation-fails-with-kernels-5-1-x/77489):
所以我还是选择了lt长期维护版， 这里是4.4.217-1.el7
```
sudo yum -y --enablerepo=elrepo-kernel install kernel-lt.x86_64 kernel-lt-devel.x86_64
```
这时候，在/etc/grub2.cfg中搜索"menuentry"能看到4.4.217的内核是在启动位置0的. 如果想哟生效，我们需要更改内核的启动顺序
```
sudo vim /etc/default/grub
# 将GRUB_DEFAULT=saved 改为GRUB_DEFAULT=0
```
重新创建一下内核配置
```
sudo grub2-mkconfig -o /boot/grub2/grub.cfg
sudo reboot
```
这时候，不出所料，图形化界面没有进去，至于kdmup那个Failed， 无关大雅. 一开始，网上查了好多资料都在说是kdump的内存分配失败，得将默认留给kdump的内存调整为128, ... 其实不然，最起码我这里不是这原因，而是因为显卡驱动，一个都没了，nouveau被屏蔽了，Nvidia在更新了内核之后是需要重新编译安装的,那么我们crtl+alt+F1进入终端模式:
```
uname -a # 内核是没问题更换了的
cd ~
sudo ./NVIDIA-Linux-x86_64-440.36.run # 用最新的驱动是没什么问题的
sudo reboot
```
这样内核更换成功，并且驱动随之升级成功了

----

接下来先让GPU可以在docker中使用吧. 
```
sudo systemctl disable firewalld.service && systemctl stop firewalld.service
# 切换到root
iptables -F && iptables -X && iptables -F -t nat && iptables -X -t nat # 清空防火墙默认策略
iptables -P FORWARD ACCEPT
swapoff -a # 关闭交换分区， 这个其实是为后面kubernetes做准备的，docker这里可以不做
sed -i 's/^SELINUX=.*/SELINUX=disabled/' /etc/selinux/config
setenforce 0
sed -i 's/^SELINUX=.*/SELINUX=disabled/' /etc/selinux/config # 关闭selinux
```
接下来需要安装docker
```
# 安装依赖
sudo yum install -y yum-utils device-mapper-persistent-data lvm2
# 添加docker的yum源，我们这里添加的是阿里的源，在国内快些
sudo yum-config-manager --add-repo http://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
# 如果想指定版本安装，那么执行这条查看
yum list docker-ce --showduplicates | sort -r
# 我们这里直接下载最新的了
sudo yum install docker-ce
```
这里就安装完成了，启动docker服务吧
```
sudo systemctl start docker && systemctl enable docker
sudo docker versio
```
执行Docker需要用户具有sudo权限，所以可以将需要使用Docker的普通用户加入docker用户组
```
sudo usermod -aG docker XXX
```
要想生效，得logout出去一次或者reboot
接下来，我们需要更改一下docker hub的源，方便在国内下载
```
sudo vim /etc/docker/daemon.json # 如果不存在就创建一个
{
  "registry-mirrors": ["https://registry.docker-cn.com"]
}
```
Docker的数据目录默认位于/var/lib/docker，里面会存储着Docker镜像的数据. 如果其所在的硬盘分区空间较小，可以将其转移到大的磁盘分区. 例如我这里是根目录/挂载在小硬盘上，/home目录挂载在大硬盘上，所以将其转移到/home目录下:
```
sudo systemctl stop docker
mkdir /home/dockerData
mv /var/lib/docker /home/dockerData
ln -s /home/dockerData/docker /var/lib/docker
sudo systemctl start docker
```

------

接下来安装Nvidia-docker
安装好了普通的Docker以后，如果想在容器内使用GPU会非常麻烦（并不是不可行），好在Nvidia为了让大家能在容器中愉快使用GPU，基于Docker开发了Nvidia-Docker，使得在容器中深度学习框架调用GPU变得极为容易, 只要安装了显卡驱动就可以(终于不用自己搞CUDA和cuDNN了).
```
# 添加相关库 切换到root用户
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.repo | tee /etc/yum.repos.d/nvidia-docker.repo
# 安装 切换到root用户
yum install -y nvidia-docker2
pkill -SIGHUP dockerd
```
测试:
```
docker run --runtime=nvidia --rm nvidia/cuda nvidia-smi
```
nvidia-docker2开始就不需要使用nvidia-docker了，而是使用--runtime来集成进了docker里, --rm意思就是执行完删除容器. 
安装完nvidia-docker后，/etc/docker/daemon.json需要重新添加国内docker hub的源
```
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    },
    "registry-mirrors": ["https://registry.docker-cn.com"]
}
```
我们既然能在容器中使用GPU了，那么我们使用容器运行Tensorflow
```
docker run --runtime=nvidia -it --rm tensorflow/tensorflow:latest-gpu \
    python -c "import tensorflow as tf; print(tf.contrib.eager.num_gpus())"
```
如果是语法错误，Tensorflow跨版本语法上会有不小的出入，自行调整一下吧. 

容器使用GPU并不会对其独占，多个容器使用GPU就如同多个程序使用GPU一样，只要协调好显存与计算力的使用即可.

-----------------------------

接下来我们开始安装K8s相关组件:
因为k8s是谷歌开源的，所以下文涉及的各种下载均需要连接谷歌服务器，而这对于我们来说是不可行的. 解决办法有两种：其一是服务器上挂代理；另外就是下载地址替换
我们添加K8s的yum源:
```
# 创建并编辑/etc/yum.repos.d/kubernetes.repo文件
[kubernetes]
name=Kubernetes
baseurl=https://mirrors.aliyun.com/kubernetes/yum/repos/kubernetes-el7-x86_64
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://mirrors.aliyun.com/kubernetes/yum/doc/yum-key.gpg https://mirrors.aliyun.com/kubernetes/yum/doc/rpm-package-key.gpg
exclude=kube*
```
安装
```
sudo yum install -y kubelet kubeadm kubectl --disableexcludes=kubernetes
```
因为有些RHEL/CentOS 7的用户报告说iptables被绕过导致流量路由出错，所以需要设置以下内容
创建并编辑/etc/sysctl.d/k8s.conf文件，输入以下内容:
```
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
```
查看是否添加成功:
```
sudo sysctl --system
```
启动kubelet服务
```
sudo systemctl enable kubelet && systemctl start kubelet
```
但是会发现，其实状态并不是running, 这是因为需要先进行master的初始化工作. 


