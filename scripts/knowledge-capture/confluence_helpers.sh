# Source this, then build the page body with heredocs + these helpers:
#   source SKILL_ROOT/scripts/knowledge-capture/confluence_helpers.sh
#   PREFIX=qa   # attachment filename prefix used in the vault
img(){  printf '<p><ac:image ac:width="900"><ri:attachment ri:filename="%s-%s.png"/></ac:image></p>' "$PREFIX" "$1"; }
code(){ printf '<ac:structured-macro ac:name="code" ac:schema-version="1"><ac:parameter ac:name="language">%s</ac:parameter><ac:plain-text-body><![CDATA[%s]]></ac:plain-text-body></ac:structured-macro>' "$1" "$2"; }
info(){ printf '<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body><p>%s</p></ac:rich-text-body></ac:structured-macro>' "$1"; }
note(){ printf '<ac:structured-macro ac:name="note" ac:schema-version="1"><ac:rich-text-body><p>%s</p></ac:rich-text-body></ac:structured-macro>' "$1"; }
toc(){  printf '<p><ac:structured-macro ac:name="toc" ac:schema-version="1"><ac:parameter ac:name="maxLevel">2</ac:parameter></ac:structured-macro></p>'; }
