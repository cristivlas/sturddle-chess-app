PATH=/usr/local/opt/openjdk@11/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
export CPPFLAGS=-I/usr/local/opt/openssl@3/include
export CFLAGS=-I/usr/local/opt/openssl@3/include
export LDFLAGS="-L/usr/local/opt/openssl@3/lib -L/usr/local/opt/openssl@1.1/lib"

export PKG_CONFIG_PATH=/usr/local/opt/openssl@3/lib/pkgconfig
