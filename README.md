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

## 开始吧
**cluster-master**

**node-***
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
chmod +x NVIDIA-Linux-x86\_64-440.36.run
sudo ./NVIDIA-Linux-x86i\_64-440.36.run
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



