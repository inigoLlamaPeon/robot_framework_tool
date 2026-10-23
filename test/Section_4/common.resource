*** Settings ***
Library    Collections

*** Variables ***
${SECTION_4_INTEGER}    ${{64}}
${SECTION_4_FLOAT}    ${{1.75}}
${SECTION_4_CHARACTER}    Q
${SECTION_4_TEXT}    sample section 4
&{SECTION_4_DATA}    section=Section 4    count=${{5}}    status=ready
${SECTION_4_LABEL}    quality check
${SECTION_4_RETRY_LIMIT}    ${{2}}
${SECTION_4_NOTE}    all checks enabled
@{SECTION_4_LIST}    draft    review    approved
${SECTION_4_TUPLE}    ${{("level-1", 48, 4.25)}}
${SECTION_4_SET}    ${{set(["cyan", "magenta", "yellow"])}}
${SECTION_4_COMBINED}    ${SECTION_4_TEXT} - ${SECTION_4_CHARACTER}