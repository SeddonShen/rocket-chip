
if [ $1 = 1 ]; then
    export all_proxy=http://172.25.16.1:7890
elif [ $1 = 2 ]; then
    export https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 all_proxy=http://127.0.0.1:7890
elif [ $1 = 3 ]; then
    export https_proxy=http://192.168.1.76:7890 http_proxy=http://192.168.1.76:7890 all_proxy=http://192.168.1.76:7890
fi

branch_checkout=false
if [ $# = 2 ]; then
    echo "Checkout"
fi

git_update() {
    branch="$1"
    git stash
    if [ $branch_checkout = true ]; then
        git checkout $branch
    fi
    git pull
    git stash pop
}

# NOOP_HOME
cd $NOOP_HOME
git_update master

# BMCFUZZ_HOME
cd $BMCFUZZ_HOME
git_update main

# $NOOP_HOME/difftest
cd $NOOP_HOME/difftest
git_update SFuzz

