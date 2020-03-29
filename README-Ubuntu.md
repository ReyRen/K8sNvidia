## 当前环境
| Hostname        |IP    | GPU数量   | 操作系统 | 内核版本 |
| --------   | -----:   | :----: | :----: | :----: |
| cluster-msater        | 192.168.0.113     |   0    | Ubuntu 18.04.3 LTS |  5.3.0-42-generic |
| node-110        | 192.168.0.110      |   1*1080Ti    |  Ubuntu 18.04.3 LTS | 5.3.0-42-generic |
| noed-109        | 192.168.0.109      |   1*1080Ti    |  Ubuntu 18.04.3 LTS | 5.3.0-42-generic |
| noed-106        | 192.168.0.106      |   1*1080Ti    |  Ubuntu 18.04.3 LTS | 5.3.0-42-generic |

## 运行环境准备

### cluster-master:

首先我们需要将防火墙, iptables等进行关闭
```
systemctl status ufw.service
sudo systemctl stop ufw.service
sudo systemctl disable ufw.service
# 切换到root
iptables -F && iptables -X && iptables -F -t nat && iptables -X -t nat # 清空防火墙默认策略
iptables -P FORWARD ACCEPT
```
接下来需要关闭交换分区
```
sudo swapon --show # 查看当前交换分区情况，如果无输出，说明交换分区已关闭或者未使用
sudo swapoff -v /swapfile # 临时关闭了
sudo vim /etc/fstab # 将/swapoff注释，这样就永久关闭了
```
我这里还有个问题就是/etc/resolv.conf总是被覆盖，导致域名解析总是出错，如果无同样的问题，可以跳过这一块儿
```
sudo apt-get install resolvconf
vim /etc/resolvconf/resolv.conf.d/head
   nameserver 8.8.8.8
   nameserver 114.114.114.114
sudo resolvconf -u # 更新配置文件
```
修改时钟
```
ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
bash -c "echo 'Asia/Shanghai' > /etc/timezone"
```
将Ubuntu的apt源替换为阿里的，这样方便下载东西
```
sudo mv /etc/apt/sources.list /etc/apt/sources.list.bak
sudo rm -f /etc/apt/sources.list.save
wget https://raw.githubusercontent.com/ReyRen/K8sNvidia/master/source.list
sudo cp -f source.list /etc/apt/sources.list
sudo apt-get update
```
安装docker
```
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
sudo curl -fsSL https://mirrors.ustc.edu.cn/docker-ce/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://mirrors.ustc.edu.cn/docker-ce/linux/ubuntu $(lsb_release -cs) stable"
sudo apt-get update
apt-cache madison docker-ce # 可以看到所能支持的docker-ce, 可以在install的时候指定版本进行下载
sudo apt-get install -y docker-ce
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker username # 将username用户添加到docker组，这样就可以非root执行docker了
```
接下来将docker hub的源地址更改为国内的，这样方便后续image的下载
```
vim /etc/docker/daemon.json
{
    "registry-mirrors": ["https://registry.docker-cn.com"]
}
```
接下来开始安装k8s组建
```
# 切换为root
curl -s https://mirrors.aliyun.com/kubernetes/apt/doc/apt-key.gpg | sudo apt-key add -
echo "deb https://mirrors.aliyun.com/kubernetes/apt/ kubernetes-xenial main" > /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update
sudo apt install -y kubelet=1.17.4-00 kubeadm=1.17.4-00 kubectl=1.17.4-00 # 也可不指定版本下载最新的
kubeadm version # 可以看到已经安装的版本
sudo systemctl enable kubelet
sudo systemctl start kubelet # 但是会发现是running不起来的，别急，这个是需要先init master的
```
接下来是我们的master初始化工作

基础命令是`kubeadm init`，不过先别着急执行

初始化Master的过程中会下载一些镜像，因为k8s很多系统组件也是以容器的方式运行。可以先执行kubeadm config images pull尝试下载一下，如果没有设置代理，那么肯定会出现网络错误，因为无法连接谷歌的服务器

关于谷歌镜像的下载解决办法有多种：
* 使用阿里云自己做一个镜像站，修改k8s配置从阿里云下载
* 使用GitHub同步结合Docker Hub Auto Build
* 手动下载镜像然后重新打tag

通过下面这个命令查看对于当前的kubernetes版本需要安装的镜像的版本

```
cd ~
kubeadm config images list > k8s_need_images.dat
```
然后使用这个脚本[retag_images.sh](https://github.com/ReyRen/K8sNvidia/blob/master/retag_images.sh)
```
wget https://raw.githubusercontent.com/ReyRen/K8sNvidia/master/retag_images.sh
chmod +x retag_images.sh
sudo ./retag_images.sh
```
我们以上用的就是阿里云的源去干这个事儿

稍等一会. 完成后使用docker images查看下，所需要的k8s镜像都已存在, 并且标签都打好了.

接下来需要将/etc/hosts进行节点名同步:

```
192.168.0.113   cluster-master
192.168.0.110   yuanren
192.168.0.109   node-109
192.168.0.106   node-106
```
还有一个在初始化过程中会出现的一个warning:
`[WARNING IsDockerSystemdCheck]: detected "cgroupfs" as the Docker cgroup driver....`
文件驱动默认由systemd改成cgroupfs, 而我们安装的docker使用的文件驱动是systemd, 造成不一致, 导致镜像无法启动
```
文件驱动默认由systemd改成cgroupfs, 而我们安装的docker使用的文件驱动是systemd, 造成不一致, 导致镜像无法启动
```
我们也能看到docker默认使用的文件驱动是cgroupfs, 那么我们在kubeadm init完成后修改一下/etc/docker/daemon.json文件就行了，问题不大
```
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "registry-mirrors": ["https://registry.docker-cn.com"]
}
```

接下来创建一个kubeadm-config.yaml文件
```
kubeadm config print init-defaults  > kubeadm-config.yaml
```
具体修改的方式参照[示例kubeadm-config](https://github.com/ReyRen/K8sNvidia/blob/master/kubeadm-config.yaml)

然后执行初始化命令
```
sudo kubeadm init --config kubeadm-config.yaml
```
接下来一小会儿的preflight check， 那么就会出现“Your Kubernetes master has initialized successfully!”说明初始化成功了, 这样的话我们看看`docker ps`和`systemctl status kubelet`会发现docker中将之前下载的image全启动了，kubelet状态为running.

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
接下来就可以等待node那边执行刚init出来的命令进行加入了. 成功加入后，稍等片刻
```
kubectl get nodes # 会发现全部是Ready状态了
```
至此，kubernetes管理起了集群搭建完了.
