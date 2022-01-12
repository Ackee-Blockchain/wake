#!/usr/bin/env bash
echo "/woke/.githooks/pre-commit.sh executing..."

ZERO=0

function run_pre_commit_for()
{
    ./"$1"/.githooks/pre-commit.sh
    if [ $? -gt $ZERO ];
    then
        exit 1;
    fi
}

for i in "woke" "woke-js" "editors/code";
do
    number=$(git diff --cached --name-only --diff-filter=ACM $i | wc -l)
    if [ $number -gt $ZERO ];
    then
        echo "calling /woke/$i/.githooks/pre-commit.sh"
        run_pre_commit_for $i
    fi
done

echo "/woke/.githooks/pre-commit.sh successfully executed."