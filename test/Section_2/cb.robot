*** Test Cases ***
Section 2 CB Basic Test
    [Documentation]    Verifies the basic test case in Section 2 file cb executes successfully.
    [Tags]    section-2    smoke
    Should Be Equal    hello    hello

Section 2 CB Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-2    regression    apple
    Should Contain    test automation    automation

Section 2 CB Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-2    regression
    Should Not Be Equal    success    failure

Section 2 CB Number Equality Test
    [Documentation]    Verifies equality for matching numeric text values.
    [Tags]    section-2    regression    bus
    Should Be Equal    17    17

Section 2 CB Exact Text Test
    [Documentation]    Verifies equality for matching sample text values.
    [Tags]    section-2    regression
    Should Be Equal    sample text    sample text