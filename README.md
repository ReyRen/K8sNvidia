# K8sNvidia
使用k8s对GPU集群进行管理

## 心路历程
如何将办公室中的GPU充分的利用与集中管理起来， 一开始也会想到openStack之类的虚拟化技术， 然后将节点组成集群，驱动穿透. 但是这样的操作成本预计资源耗费成本过于庞大. 无心之中发现了Nvidia-docker,也见识了K8s进行管理的强大之处. 索性将Nvidia-docker交由K8s进行管理。此种想法已在两年前就有了，网上的资料原理大致相同，但是由于版本过于陈旧或者叙述不够详尽等问题，着实让我在坑中挣扎很久. 所以， 这不是创新，而是一些解决方案的记录，错误的解决历程，宏观层面一些东西的原理性解释.  以此送给健忘的我. 

## 当前环境
| Hostname        |IP    | GPU数量   | 操作系统 | 内核版本 | 
| --------   | -----:   | :----: | :----: | :----: |
| cluster-msater        | 192.168.0.113     |   0    | CentOS Linux release 7.7.1908 (Core) | 3.10.0-1062.18.1.el7.x86_64 |
| node-110        | 192.168.0.110      |   1*1080Ti    | CentOS Linux release 7.7.1908 (Core) | 3.10.0-1062.18.1.el7.x86_64 |
| noed-109        | 192.168.0.109      |   1*1080Ti    | CentOS Linux release 7.7.1908 (Core) | 3.10.0-1062.18.1.el7.x86_64 |
| noed-106        | 192.168.0.106      |   1*1080Ti    | CentOS Linux release 7.7.1908 (Core) | 3.10.0-1062.18.1.el7.x86_64 |
| node-105        | 912.168.0.105      |   1*1080Ti    | Ubuntu 18.04.3 LTS | 5.3.0-40.x86_64 |


**NOTE**

经测试，内核版本不同的情况下，比如Ubuntu18默认的5.3的内核的节点加入Centos-4.4组成的集群中，是加入不成功的. Flannel网络的pod创建是失败的. 
至于原因呢，可能涉及到内核版本跨度很大(虽然docker, nvidia-docker, k8s的版本是相同的), 另一个是不同发行版的内核都是进行修饰过的特制内核. 
所以也就不再这上面浪费时间了.

我们需要做到的就是操作系统发行版和内核版本在集群中保持一致. 

以下的操作是在centos-7.6-1908上执行的(内包含升级内核到4.4), 如果操作系统是Ubuntu-18.04.3(内核版本是5.3.0-40), 请移位至[Ubuntu18版本](https://github.com/ReyRen/K8sNvidia/blob/master/README-Ubuntu.md)


## 规划
cluster-master作为k8s的master节点不参与训练，只是用来分配pod

node-110 node-109 node-106用来作为pod迁移节点

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

可以参考一下[Nvidia-forums](https://forums.developer.nvidia.com/t/installation-fails-with-kernels-5-1-x/77489):

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

-------

接下来是安装docker环境
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
接下来先做一些防火墙, iptables, selinux的关闭
```
sudo systemctl disable firewalld.service && systemctl stop firewalld.service
#防火墙永久关闭, 如果显示无服务的话就算了
sudo chkconfig iptables off
# 切换到root
iptables -F && iptables -X && iptables -F -t nat && iptables -X -t nat # 清空防火墙默认策略
iptables -P FORWARD ACCEPT
swapoff -a # 关闭交换分区， 这个其实是为后面kubernetes做准备的，docker这里可以不做
sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
setenforce 0
sed -i 's/^SELINUX=.*/SELINUX=disabled/' /etc/selinux/config # 关闭selinux
```
这里就安装完成了，启动docker服务吧
```
sudo systemctl start docker && systemctl enable docker
sudo docker version
```
执行Docker需要用户具有sudo权限，所以可以将需要使用Docker的普通用户加入docker用户组
```
sudo usermod -aG docker XXX
```
要想生效，得logout出去一次或者reboot

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

接下来是我们的master初始化工作

基础命令是`kubeadm init`，不过先别着急执行

初始化Master的过程中会下载一些镜像，因为k8s很多系统组件也是以容器的方式运行。可以先执行kubeadm config images pull尝试下载一下，如果没有设置代理，那么肯定会出现网络错误，因为无法连接谷歌的服务器

关于谷歌镜像的下载解决办法有多种：

    * 使用阿里云自己做一个镜像站，修改k8s配置从阿里云下载
    * 使用GitHub同步结合Docker Hub Auto Build
    * 手动下载镜像然后重新打tag

另外附[Google所有镜像](https://console.cloud.google.com/gcr/images/google-containers)

通过下面这个命令查看对于当前的kubernetes版本需要安装的镜像的版本
```
cd ~
kubeadm config images list > k8s_need_images.dat
```
然后将其放入到了k8s_need_images

然后使用这个脚本[retag_images.sh](https://github.com/ReyRen/K8sNvidia/blob/master/retag_images.sh)
```
wget https://raw.githubusercontent.com/ReyRen/K8sNvidia/master/retag_images.sh
sh retag_images.sh   
```
我们以上用的就是阿里云的源去干这个事儿

稍等一会. 完成后使用docker images查看下，所需要的k8s镜像都已存在, 并且标签都打好了. 

接下来我们需要做一个很重要片的事儿，特别坑

那就同步系统时钟，否则，会node节点是死活加入不到master的，并且报的错误是balabala x509认证错误，网上解决反感都是说的是token过期, 当重新生产token还出现这个问题，那就是时钟问题了. [kubernetes-issue:58921](https://github.com/kubernetes/kubernetes/issues/58921#issuecomment-466362170)这个三哥一语道破
```
timedatectl set-timezone Asia/Shanghai
systemctl enable chronyd
systemctl start chronyd
# 将当前的 UTC 时间写入硬件时钟
timedatectl set-local-rtc 0
# 重启依赖于系统时间的服务
systemctl restart rsyslog 
systemctl restart crond
```
接下来需要将/etc/hosts进行节点名同步:
```
192.168.0.113   cluster-master
192.168.0.110   node-110
192.168.0.109   node-109
192.168.0.106   node-106
```
我们需要创建一个默认的kubeadm-config.yaml文件在master上:
```
kubeadm config print init-defaults  > kubeadm-config.yaml
```
可以参考[kubeadm-config](https://github.com/ReyRen/K8sNvidia/blob/master/kubeadm-config.yaml)
进行一些简单的修改

然后执行
```
sudo kubeadm config images pull --config kubeadm-config.yaml
```
其中可能会有个warning

[WARNING IsDockerSystemdCheck]: detected "cgroupfs" as the Docker cgroup driver....

文件驱动默认由systemd改成cgroupfs, 而我们安装的docker使用的文件驱动是systemd, 造成不一致, 导致镜像无法启动
```
docker info | grep Cgroup
```
我们也能看到docker默认使用的文件驱动是cgroupfs, 那么我们在kubeadm init完成后修改一下`/etc/docker/daemon.json`文件就行了，问题不大
```
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "registry-mirrors": ["https://registry.docker-cn.com"]
}
```
接下来一小会儿的preflight check， 那么就会出现“Your Kubernetes master has initialized successfully!”说明初始化成功了, 这样的话我们看看`docker ps`和'systemctl status kubelet'会发现docker中将之前下载的image全启动了，kubelet状态为running. 

**PS:** 如果由于你重新启动docker, 或者某种原因想重新初始化一下master, 那么需要做一些工作:
```
sudo kubeadm reset
rm -rf $HOME/.kube/config # 如果之前创建过，一定要做这一步，reset是不会给你删除的，不然是初始化不成功的
```
为了让非root用户也能使用kubectl来管理k8s集群，需要执行以下命令：
```
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
```
接下来我们查看一些状态:
```
kubectl get cs # 查看组件状态, 都为healthy
kubectl get nodes # 查看节点状态
kubectl get pods -n kube-system # 查看kubernetes管理的kube-system命名空间的pods状态
```
在这里发现两个问题:
* coredns的pod是pending状态: 这是因为需要node节点的加入, 但是还没有让node加入，所以为pending
* master node的状态为Notready: 这是因为还没有安装网络插件

接下来我们就需要安装网络插件, 到目前，node和master是不会有网络通讯的, 目前最流行的Kubernetes网络插件有Flannel、Calico、Canal、Weave 这里选择使用flannel. 

在cluster-master节点上执行:
```
wget https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml
sed -i 's@quay.io@quay.azk8s.cn@g' kube-flannel.yml
kubectl apply -f kube-flannel.yml
kubectl get pods -n kube-system # 稍等片刻会发现有了flannel的pods并且running起来了
kubectl get nodes # 状态也变成Ready了
```
接下来就可以等待node那边执行刚init出来的命令进行加入了. 
成功加入后，稍等片刻
```
kubectl get nodes # 会发现全部是Ready状态了
```

至此，kubernetes管理起了集群搭建完了. 


接下来高一个dashboard吧
可以参考最新[官方recommended.ymal](https://github.com/kubernetes/dashboard/#getting-started)
```
wget https://raw.githubusercontent.com/kubernetes/dashboard/v2.0.0-rc4/aio/deploy/recommended.yaml
mv recommended.yaml dashboard-recommended.yaml 
kubectl apply -f dashboard-recommended.yaml
```
在全部创建好后
```
kubectl get pods -n kubernetes-dashboard
kubectl get pods --all-namespaces
```
会看到都是running状态

从1.7开始，dashboard只允许通过https访问，如果使用kube proxy则必须监听localhost 或 127.0.0.1. 对于NodePort没有这个限制，但是仅建议在开发环境中使. 对于不满足这些条件的登录访问, 在登录成功后浏览器不跳转，始终停在登录界面

我们为了让别的机器也能访问，所以，启用了端口转发来访问dashboard:
```
kubectl port-forward -n kubernetes-dashboard  svc/kubernetes-dashboard 4443:443 --address 0.0.0.0
```
这样通过访问`https://192.168.0.113:4443`就能访问了，但是是需要token的, 所以我们创建一个用户，并赋予cluster-admin的最高权限然后生成token

第一次执行需要:
```
kubectl create sa dashboard-admin -n kube-system
kubectl create clusterrolebinding dashboard-admin --clusterrole=cluster-admin --serviceaccount=kube-system:dashboard-admin
```
然后使用
```
wget https://raw.githubusercontent.com/ReyRen/K8sNvidia/master/token_regenerate.sh
sh token_regenerate.sh
```
即可登陆进去了. 

但是通过上面的port forward未免有点麻烦, kubernetes是支持NodePort方法的:
```
kubectl get deployments -A # 查看一下dashboard的service namespace
kubectl -n kube-system edit service kubernetes-dashboard --namespace=kubernetes-dashboard
```
进入编辑页面后, 将`type: ClusterIP` 修改为 `type: NodePort`保存
```
kubectl -n kube-system get service kubernetes-dashboard --namespace=kubernetes-dashboard
```
可以查看到自动生成的段口号，所以可以直接使用那个段口号访问了. 


关于如何移除Kubernetes dashboard资源从我的deployment中的问题(这个可以作为dashboard部署失败想重新部署或者移除其他deployment的样例):
```
kubectl get service -A # 查看是什么namespace
```
然后
```
kubectl delete deployment kubernetes-dashboard  --namespace=kubernetes-dashboard
kubectl delete deployment dashboard-metrics-scraper --namespace=kubernetes-dashboard
```
如果有service的话，做同样的事情
```
kubectl get service -A
```
```
kubectl delete service kubernetes-dashboard  --namespace=kubernetes-dashboard
kubectl delete service dashboard-metrics-scraper  --namespace=kubernetes-dashboard
```
最后是删除service account和密码:
```
kubectl delete sa kubernetes-dashboard --namespace=kubernetes-dashboard
kubectl delete secret kubernetes-dashboard-certs --namespace=kubernetes-dashboard
kubectl delete secret kubernetes-dashboard-key-holder --namespace=kubernetes-dashboard
```

----------------

接下来需要用k8s管理GPU了，这也是最终目的

自从k8s 1.8版本开始，官方开始推荐使用device plugin的方式来调用GPU使用. 截至目前, Nvidia和AMD都推出了相应的设备插件, 使得k8s调用GPU变得容易起来. 因为我们是Nvidia的显卡, 所以需要安装NVIDIA GPUdevice plugin

在这里需要提前说明两个参数，--feature-gates="Accelerators=true"和--feature-gates="DevicePlugins=true"。在很多教程中都说明若要使用GPU，需要设置Accelerators为true，而实际上该参数在1.11版本之后就弃用了. 而将DevicePlugins设置为true也是在1.9版本之前需要做的事情，在1.10版本之后默认就为true. 所以对于我们来说，因为使用的是1.17版本，这两个feature-gates都不需要做设置.

当node节点上修改万/etc/docker/daemon.json并且重启docker后

master执行

```
kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/1.0.0-beta4/nvidia-device-plugin.yml
```
然后通过
```
kubectl describe nodes
```
可以查看到能使用的GPU资源节点详细信息

修改Docker默认的runtime, 修改/etc/docker/daemon.json, 加入
```
"default-runtime": "nvidia",
```
然后记得重新启动docker



### node-*:
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
#防火墙永久关闭, 如果显示无服务的话就算了
sudo chkconfig iptables off
# 切换到root
iptables -F && iptables -X && iptables -F -t nat && iptables -X -t nat # 清空防火墙默认策略
iptables -P FORWARD ACCEPT
swapoff -a # 关闭交换分区， 这个其实是为后面kubernetes做准备的，docker这里可以不做
sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
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
sudo docker version
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

接下来我们需要做一个很重要片的事儿, 那就同步系统时钟，否则，会node节点是死活加入不到master的，并且报的错误是balabala x509认证错误，网上解决反感都是说的是token过期, 当重新生产token还出现这个问题，那就是时钟问题了
```
timedatectl set-timezone Asia/Shanghai
systemctl enable chronyd
systemctl start chronyd
# 将当前的 UTC 时间写入硬件时钟
timedatectl set-local-rtc 0
# 重启依赖于系统时间的服务
systemctl restart rsyslog 
systemctl restart crond
```
接下来需要将/etc/hosts进行节点名同步:
```
192.168.0.113   cluster-master
192.168.0.110   node-110
192.168.0.109   node-109
192.168.0.106   node-106
```
当cluster-master上的`kubectl get pods -n kube-system`以及`kubectl get nodes`得到上面master部署部分的正确反馈后，node节点开始加入:
```
sudo kubeadm join XXX:6443 --token XXX --discovery-token-ca-cert-hash XXX # 按照上面master init输出内容执行
```
当出现“This node has joined the cluster:”说明加入成功了. 

当然在这加入的preflight check中可能会出现"[WARNING IsDockerSystemdCheck]: detected "cgroupfs" as the Docker cgroup driver...."

```
 "exec-opts": ["native.cgroupdriver=systemd"], #将这个加入到/etc/docker/daemon.json中
```

在使用k8s-device-plugin时，node节点上需要做的是

修改Docker默认的runtime, 修改/etc/docker/daemon.json, 加入
```
"default-runtime": "nvidia",
```
然后记得重新启动docker



----------------

----------------

------------------

----------------

测试: 

在cluster-master节点上创建tf-pod.ymal
```
apiVersion: v1
kind: Pod
metadata:
  name: tf-pod
spec:
  containers:
    - name: tf-container
      image: tensorflow/tensorflow:latest-gpu
      resources:
        limits:
          nvidia.com/gpu: 1 # requesting 1 GPUs
```
执行`kubectl apply -f ~/tf-pod.yaml`创建Pod. 使用`kubectl get pod`可以看到该Pod已经启动成功
如果想看这个pod的详细启动过程
```
kubectl describe pod xxx
```
进入pod内部就是通过执行`kubectl exec tf-pod -it -- bash`


**关于pod报错:"Back-off restarting failed container"**
这是因为你的容器内部其实已经`exit code 0`退出了, 这个表明没有任何错误的退出, 是因为pod默认的生命周期是很短的. 

所以你应加一句
```
command: [ "/bin/bash", "-ce", "tail -f /dev/null" ] # 在image底下
```
**关于第一次新加入节点重启动docker会发现该flannel,proxy, device-plugin失败的问题**
如果出现以上问题，需要的是将新加入的node节点进行重直然后重新加入:
```
kube reset
rm -rf $HOME/...
join balabalabala
```

**关于想要重新生成新的join msg的问题**
```
 kubeadm token list # 用于查看当前可用的token
 kubeadm token create # 会生成一个新的token
 openssl x509 -pubkey -in /etc/kubernetes/pki/ca.crt | openssl rsa -pubin -outform der 2>/dev/null | openssl dgst -sha256 --hex | sed 's/^.* //'   # 会生成新的hash秘钥
```

**关于报错**"Warning FailedCreatePodSandBox 25s (x16 over 8m53s) kubelet, node-106 Failed to create pod sandbox: rpc error: code = Unknown desc = failed pulling image "k8s.gcr.io/pause:3.2": Error response from daemon: Get https://k8s.gcr.io/v2/: net/http: request canceled while waiting for connection (Client.Timeout exceeded while awaiting headers)"

这个报错是通过在master上看到node-106一直是NotReady状态, 并且在node上`docker ps`一直都是空的. 当使用`kubectl get pods -n kube-system`查看master上的pod状态时，proxy和flannel是挂了的, 一个是"containercreating"， 一个是"init0/1".

于是使用`kubectl describe pod kube-proxy-XX --namespace=kube-system`看到这个pod的具体的信息, 发现是从谷歌拉取

```
k8s.gcr.io/pause:XX
k8s.gcr.io/kube-proxy:vXX
```
的时候被墙了.

所以我们同样使用上面master的办法，但是只需要flannel和proxy两个即可，提前将他们拉下来

然后node上执行`sudo kubeadm reset`, 然后master上`kubectl delete node node-106`提出去， 重新join就会发现完美了.


**关于查看k8s系统级别日志**
```
sudo journalctl -f -u kubelet
```
