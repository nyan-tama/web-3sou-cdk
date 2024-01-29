
```
$ docker build -t aws-cdk .
```

```
$ sudo docker run --rm -it -v ~/.aws:/root/.aws -v ${PWD}:/root/work aws-cdk
```

```
$ pip install -r requirements.txt
```

```
#AWS構築の場合
$ cdk deploy -v
```

```
#AWS削除の場合
$ cdk destroy -v
```

```
# EC2への接続 AWSのSSMを利用
$ aws ssm start-session --target EC2のinstance-id
$ sudo su - ec2-user
```