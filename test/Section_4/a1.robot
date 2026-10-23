*** Test Cases ***
Section 4 A1 Basic Test
    [Documentation]    Verifies the basic test case in Section 4 file a1 executes successfully.
    [Tags]    section-4    smoke
    Should Be Equal    hello    hello

Section 4 A1 Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-4    regression
    Should Contain    data validation    validation

Section 4 A1 Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-4    regression
    Should Not Be Equal    valid    invalid

Section 4 A1 Exact Text Test
    [Documentation]    Verifies equality for matching sample text values.
    [Tags]    section-4    regression
    Should Be Equal    check complete    check complete

Section 4 A1 Number Equality Test
    [Documentation]    Verifies equality for matching numeric text values.
    [Tags]    section-4    regression
    Should Be Equal    8    8

Section 4 Command Line Variables Test
    [Documentation]    Verifies user-defined variables can be supplied to the Robot Framework run.
    [Tags]    section-4    variables
    Log    ENV=${ENV}
    Log    USER=${USER}
    Log    TIMEOUT=${TIMEOUT}
    Log    ${CLI_TEXT}
    Log Many    @{CLI_LIST}
    Log    ${CLI_SET}
    Log    ${CLI_TUPLE}
    Log    ${CLI_DICTIONARY}