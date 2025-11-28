
docker stop $(docker ps -a -q)
docker rm $(docker ps -a -q)
docker system prune
docker volume prune
docker system prune -a --volumes -f
docker rm -f $(docker ps -a -q)
docker rmi -f $(docker images -a -q)
docker volume rm $(docker volume ls -q)
docker builder prune -a -f

