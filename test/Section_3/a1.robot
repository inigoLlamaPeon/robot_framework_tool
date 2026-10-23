*** Test Cases ***
Section 3 A1 Basic Test
    [Documentation]    Verifies the basic test case in Section 3 file a1 executes successfully.
    [Tags]    section-3    smoke
    Should Be Equal    hello    hello

Section 3 A1 Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-3    regression
    Should Contain    simple test case    test

Section 3 A1 Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-3    regression
    Should Not Be Equal    first    second

Section 3 A1 Number Equality Test
    [Documentation]    Verifies equality for matching numeric text values.
    [Tags]    section-3    regression
    Should Be Equal    100    100

Section 3 Command Line Variables Test
    [Documentation]    Verifies user-defined variables can be supplied to the Robot Framework run.
    [Tags]    section-3    variables
    Log    ENV=${ENV}
    Log    USER=${USER}
    Log    TIMEOUT=${TIMEOUT}
    Log    ${CLI_TEXT}
    Log Many    @{CLI_LIST}
    Log    ${CLI_SET}
    Log    ${CLI_TUPLE}
    Log    ${CLI_DICTIONARY}