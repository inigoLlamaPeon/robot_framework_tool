*** Test Cases ***
Section 3 A3 Basic Test
    [Documentation]    Verifies the basic test case in Section 3 file a3 executes successfully.
    [Tags]    section-3    smoke
    Should Be Equal    hello    hello

Section 3 A3 Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-3    regression
    Should Not Be Equal    draft    published

Section 3 A3 Exact Text Test
    [Documentation]    Verifies equality for matching sample text values.
    [Tags]    section-3    regression
    Should Be Equal    simple check    simple check