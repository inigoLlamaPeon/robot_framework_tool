*** Test Cases ***
Section 2 CC Basic Test
    [Documentation]    Verifies the basic test case in Section 2 file cc executes successfully.
    [Tags]    section-2    smoke
    Should Be Equal    hello    hello

Section 2 CC Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-2    regression    taxi
    Should Contain    quality check    quality