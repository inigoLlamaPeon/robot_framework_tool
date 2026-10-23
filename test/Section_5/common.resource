*** Settings ***
Library    Collections

*** Variables ***
${SECTION_5_INTEGER}    ${{11}}
${SECTION_5_FLOAT}    ${{9.5}}
${SECTION_5_CHARACTER}    F
${SECTION_5_TEXT}    sample section 5
&{SECTION_5_DATA}    section=Section 5    count=${{6}}    status=ready
${SECTION_5_LABEL}    final verification
${SECTION_5_RETRY_LIMIT}    ${{4}}
${SECTION_5_NOTE}    all checks completed
${SECTION_5_RESULT}    successful run
${SECTION_5_VERSION}    ${{1.0}}
@{SECTION_5_LIST}    prepare    execute    report
${SECTION_5_TUPLE}    ${{("final", 96, 5.75)}}
${SECTION_5_SET}    ${{set(["bronze", "silver", "gold"])}}
${SECTION_5_COMBINED}    ${SECTION_5_TEXT} - ${SECTION_5_CHARACTER}