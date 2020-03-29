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

如果想要删除docker中的已有的k8s容器，需要做的是，先要停止kubelet服务，否则，删除完会立马重新创建
```
sudo systemctl stop kubelet.service
docker stop $(docker ps -aq) # 停止容器
docker rm $(docker ps -aq) # 删除所有的容器
docker rmi $(docker images -q) # 删除所有的image
```

当node节点加入后， 接下来需要用k8s管理GPU了，这也是最终目的

自从k8s 1.8版本开始，官方开始推荐使用device plugin的方式来调用GPU使用. 截至目前, Nvidia和AMD都推出了相应的设备插件, 使得k8s调用GPU变得容易起来. 因为我们是Nvidia的显卡, 所以需要安装NVIDIA GPUdevice plugin

在这里需要提前说明两个参数，--feature-gates="Accelerators=true"和--feature-gates="DevicePlugins=true"。在很多教程中都说明若要使用GPU，需要设置Accelerators为true，而实际上该参数在1.11版本之后就弃用了. 而将DevicePlugins设置为true也是在1.9版本之前需要做的事情，在1.10版本之后默认就为true. 所以对于我们来说，因为使用的是1.18版本，这两个feature-gates都不需要做设置.

```
kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/1.0.0-beta4/nvidia-device-plugin.yml
```
然后通过
```
kubectl describe nodes
```
可以查看到能使用的GPU资源节点详细信息


----------------
----------------
----------------


### node-*:

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
接下来安装Nvidia显卡驱动程序
```
lsmod | grep nouveau # 查看是否有加载nouveau驱动模块儿，有输出就需要将他屏蔽
# 使用root
echo -e "blacklist nouveau\noptions nouveau modset=0" >> /etc/modprobe.d/blacklist.conf

sudo reboot
```
安装编译工具
```
sudo apt-get install gcc make
```
接下来切换到终端控制，然后执行下载好的驱动程序
```
sudo init 3
chmod +x NVIDIA-Linux-x86_64-440.36.run
sudo ./NVIDIA-Linux-x86_64-440.36.run
nvidia-smi
```
接下来需要安装nvidia-docker
安装好了普通的Docker以后，如果想在容器内使用GPU会非常麻烦（并不是不可行），好在Nvidia为了让大家能在容器中愉快使用GPU，基于Docker开发了Nvidia-Docker，使得在容器中深度学习框架调用GPU变得极为容易, 只要安装了显卡驱动就可以(终于不用自己搞CUDA和cuDNN了).
```
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
# 切换到root
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | tee /etc/apt/sources.list.d/
nvidia-docker.list
sudo apt-get update
sudo apt-get install nvidia-docker2
pkill -SIGHUP dockerd
```
按照默认方式安装完nvidia-docker2后，会将`/etc/docker/daemon.json`冲掉, 所以重新写为:
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
记得重启一下docker.service

检验:
```
docker run --runtime=nvidia --rm nvidia/cuda nvidia-smi
```
接下来安装k8s组建
```
# 切换为root
curl -s https://mirrors.aliyun.com/kubernetes/apt/doc/apt-key.gpg | sudo apt-key add -
echo "deb https://mirrors.aliyun.com/kubernetes/apt/ kubernetes-xenial main" > /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update
sudo apt install -y kubelet=1.17.4-00 kubeadm=1.17.4-00 kubectl=1.17.4-00 # 也可不指定版本下载最新的
kubeadm version # 可以看到已经安装的版本
sudo systemctl enable kubelet
sudo systemctl start kubelet # 但是会发现是running不起来的, 别急， join到已经有的master就可以自动起来了
```
在join之前，更新一下`/etc/hosts`:
```
192.168.0.113   cluster-master
192.168.0.110   yuanren
192.168.0.109   node-109
192.168.0.106   node-106
```
另外对`/etc/docker/daemon.json`我们再加两条:
```
"exec-opts": ["native.cgroupdriver=systemd"],
"default-runtime": "nvidia",
```
然后执行join命令就行, 如果忘记了token和ca, 那就在master重新生成一下:
```
kubeadm token list # 用于查看当前可用的token
kubeadm token create # 会生成一个新的token
openssl x509 -pubkey -in /etc/kubernetes/pki/ca.crt | openssl rsa -pubin -outform der 2>/dev/null | openssl dgst -sha256 --hex | sed 's/^.* //'   # 会生成新的hash秘钥
udo kubeadm join XXX:6443 --token XXX --discovery-token-ca-cert-hash sha256:XXX
```
**关于报错**
"Warning  FailedCreatePodSandBox  25s (x16 over 8m53s)  kubelet, node-106  Failed to create pod sandbox: rpc error: code = Unknown desc = failed pulling image "k8s.gcr.io/pause:3.2": Error response from daemon: Get https://k8s.gcr.io/v2/: net/http: request canceled while waiting for connection (Client.Timeout exceeded while awaiting headers)"

这个报错是通过在master上看到node-106一直是NotReady状态, 并且在node上`docker ps`一直都是空的. 
当使用`kubectl get pods -n kube-system`查看master上的pod状态时，proxy和flannel是挂了的, 一个是"containercreating"， 一个是"init0/1". 

于是使用`kubectl describe pod kube-proxy-XX --namespace=kube-system` 看到这个pod的具体的信息, 发现是从谷歌拉取
```
k8s.gcr.io/pause:XX
k8s.gcr.io/kube-proxy:vXX
```
的时候被墙了. 

所以我们同样使用上面master的办法，但是只需要flannel和proxy两个即可，提前将他们拉下来

然后node上执行`sudo kubeadm reset`, 然后master上`kubectl delete node node-106`提出去， 重新join就会发现完美了. 

