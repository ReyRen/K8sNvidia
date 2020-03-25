#!/bin/bash
images=(`cat ~/k8s_need_images.dat`)
username=registry.cn-hangzhou.aliyuncs.com/google_containers
#echo ${images[@]}
for img in ${images[@]}
do
	# 之后还有需要下载的镜像，直接在k8s_need_images.txt文件中添加即可
	# 不需要下载的（比如之前添加过的）前加上#号即可
	# 镜像名既支持k8s.gcr.io开头的，也支持gcr.io/google_containers开头的
        if [[ "${img:0:1}"x != "#"x ]]; then
                img_name=`echo $img | awk -F '/' '{print $NF}'`
		docker pull ${username}/${img_name}
		docker tag ${username}/${img_name} k8s.gcr.io/${img_name}
		#docker tag ${username}/${img_name} gcr.io/google_containers/${img_name}
		docker rmi ${username}/${img_name}
        fi
done
