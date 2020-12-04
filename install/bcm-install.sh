# download the latest version of the library, say bcm2835-1.xx.tar.gz, then:
wget http://www.airspayce.com/mikem/bcm2835/bcm2835-1.68.tar.gz
tar zxvf bcm2835-1.68.tar.gz
cd bcm2835-1.68
./configure
make
sudo make check
sudo make install
cd src
gcc -shared -o libbcm2835.so -fPIC bcm2835.c
cp libbcm2835.so /usr/local/lib
cd ../..
rm bcm2835-1.68.tar.gz
