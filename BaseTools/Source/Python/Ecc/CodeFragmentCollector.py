## @file
# preprocess source file
#
#  Copyright (c) 2007 - 2018, Intel Corporation. All rights reserved.<BR>
#
#  SPDX-License-Identifier: BSD-2-Clause-Patent
#

##
# Import Modules
#

from __future__ import print_function
from __future__ import absolute_import
import re
import Common.LongFilePathOs as os
import sys
if sys.version_info.major == 3:
    import antlr4 as antlr
    from Ecc.CParser4.CLexer import CLexer
    from Ecc.CParser4.CParser import CParser
else:
    import antlr3 as antlr
    antlr.InputStream = antlr.StringStream
    from Ecc.CParser3.CLexer import CLexer
    from Ecc.CParser3.CParser import CParser


from Ecc import FileProfile
from Ecc.CodeFragment import Comment
from Ecc.CodeFragment import PP_Directive
from Ecc.ParserWarning import Warning


##define T_CHAR_SPACE                ' '
##define T_CHAR_NULL                 '\0'
##define T_CHAR_CR                   '\r'
##define T_CHAR_TAB                  '\t'
##define T_CHAR_LF                   '\n'
##define T_CHAR_SLASH                '/'
##define T_CHAR_BACKSLASH            '\\'
##define T_CHAR_DOUBLE_QUOTE         '\"'
##define T_CHAR_SINGLE_QUOTE         '\''
##define T_CHAR_STAR                 '*'
##define T_CHAR_HASH                 '#'

(T_CHAR_SPACE, T_CHAR_NULL, T_CHAR_CR, T_CHAR_TAB, T_CHAR_LF, T_CHAR_SLASH, \
T_CHAR_BACKSLASH, T_CHAR_DOUBLE_QUOTE, T_CHAR_SINGLE_QUOTE, T_CHAR_STAR, T_CHAR_HASH) = \
(' ', '\0', '\r', '\t', '\n', '/', '\\', '\"', '\'', '*', '#')

SEPERATOR_TUPLE = ('=', '|', ',', '{', '}')

(T_COMMENT_TWO_SLASH, T_COMMENT_SLASH_STAR) = (0, 1)

(T_PP_INCLUDE, T_PP_DEFINE, T_PP_OTHERS) = (0, 1, 2)

## The collector for source code fragments.
#
# PreprocessFile method should be called prior to ParseFile
#
# GetNext*** procedures mean these procedures will get next token first, then make judgement.
# Get*** procedures mean these procedures will make judgement on current token only.
#
class CodeFragmentCollector:
    ## The constructor
    #
    #   @param  self        The object pointer
    #   @param  FileName    The file that to be parsed
    #
    def __init__(self, FileName):
        self.Profile = FileProfile.FileProfile(FileName)
        self.Profile.FileLinesList.append(T_CHAR_LF)
        self.FileName = FileName
        self.CurrentLineNumber = 1
        self.CurrentOffsetWithinLine = 0
        self.TokenReleaceList = []

    ## __EndOfFile() method
    #
    #   Judge current buffer pos is at file end
    #
    #   @param  self        The object pointer
    #   @retval True        Current File buffer position is at file end
    #   @retval False       Current File buffer position is NOT at file end
    #
    def __EndOfFile(self):
        NumberOfLines = len(self.Profile.FileLinesList)
        SizeOfLastLine = NumberOfLines
        if NumberOfLines > 0:
            SizeOfLastLine = len(self.Profile.FileLinesList[-1])

        if self.CurrentLineNumber == NumberOfLines and self.CurrentOffsetWithinLine >= SizeOfLastLine - 1:
            return True
        elif self.CurrentLineNumber > NumberOfLines:
            return True
        else:
            return False

    ## Rewind() method
    #
    #   Reset file data buffer to the initial state
    #
    #   @param  self        The object pointer
    #
    def Rewind(self):
        self.CurrentLineNumber = 1
        self.CurrentOffsetWithinLine = 0

    ## __GetOneChar() method
    #
    #   Move forward one char in the file buffer
    #
    #   @param  self        The object pointer
    #
    def __GetOneChar(self):
        if self.CurrentOffsetWithinLine == len(self.Profile.FileLinesList[self.CurrentLineNumber - 1]) - 1:
                self.CurrentLineNumber += 1
                self.CurrentOffsetWithinLine = 0
        else:
                self.CurrentOffsetWithinLine += 1

    ## __CurrentChar() method
    #
    #   Get the char pointed to by the file buffer pointer
    #
    #   @param  self        The object pointer
    #   @retval Char        Current char
    #
    def __CurrentChar(self):
        CurrentChar = self.Profile.FileLinesList[self.CurrentLineNumber - 1][self.CurrentOffsetWithinLine]
#        if CurrentChar > 255:
#            raise Warning("Non-Ascii char found At Line %d, offset %d" % (self.CurrentLineNumber, self.CurrentOffsetWithinLine), self.FileName, self.CurrentLineNumber)
        return CurrentChar

    ## __NextChar() method
    #
    #   Get the one char pass the char pointed to by the file buffer pointer
    #
    #   @param  self        The object pointer
    #   @retval Char        Next char
    #
    def __NextChar(self):
        if self.CurrentOffsetWithinLine == len(self.Profile.FileLinesList[self.CurrentLineNumber - 1]) - 1:
            return self.Profile.FileLinesList[self.CurrentLineNumber][0]
        else:
            return self.Profile.FileLinesList[self.CurrentLineNumber - 1][self.CurrentOffsetWithinLine + 1]

    ## __SetCurrentCharValue() method
    #
    #   Modify the value of current char
    #
    #   @param  self        The object pointer
    #   @param  Value       The new value of current char
    #
    def __SetCurrentCharValue(self, Value):
        self.Profile.FileLinesList[self.CurrentLineNumber - 1][self.CurrentOffsetWithinLine] = Value

    ## __SetCharValue() method
    #
    #   Modify the value of current char
    #
    #   @param  self        The object pointer
    #   @param  Value       The new value of current char
    #
    def __SetCharValue(self, Line, Offset, Value):
        self.Profile.FileLinesList[Line - 1][Offset] = Value

    ## __CurrentLine() method
    #
    #   Get the list that contains current line contents
    #
    #   @param  self        The object pointer
    #   @retval List        current line contents
    #
    def __CurrentLine(self):
        return self.Profile.FileLinesList[self.CurrentLineNumber - 1]

    ## PreprocessFile() method
    #
    #   Preprocess file contents, replace comments with spaces.
    #   In the end, rewind the file buffer pointer to the beginning
    #   BUGBUG: No !include statement processing contained in this procedure
    #   !include statement should be expanded at the same FileLinesList[CurrentLineNumber - 1]
    #
    #   @param  self        The object pointer
    #
    def PreprocessFile(self):

        self.Rewind()
        InComment = False
        DoubleSlashComment = False
        HashComment = False
        PPExtend = False
        CommentObj = None
        PPDirectiveObj = None
        # HashComment in quoted string " " is ignored.
        InString = False
        InCharLiteral = False

        self.Profile.FileLinesList = [list(s) for s in self.Profile.FileLinesListFromFile]
        while not self.__EndOfFile():

            if not InComment and self.__CurrentChar() == T_CHAR_DOUBLE_QUOTE:
                InString = not InString

            if not InComment and self.__CurrentChar() == T_CHAR_SINGLE_QUOTE:
                InCharLiteral = not InCharLiteral
            # meet new line, then no longer in a comment for // and '#'
            if self.__CurrentChar() == T_CHAR_LF:
                if HashComment and PPDirectiveObj is not None:
                    if PPDirectiveObj.Content.rstrip(T_CHAR_CR).endswith(T_CHAR_BACKSLASH):
                        PPDirectiveObj.Content += T_CHAR_LF
                        PPExtend = True
                    else:
                        PPExtend = False

                EndLinePos = (self.CurrentLineNumber, self.CurrentOffsetWithinLine)

                if InComment and DoubleSlashComment:
                    InComment = False
                    DoubleSlashComment = False
                    CommentObj.Content += T_CHAR_LF
                    CommentObj.EndPos = EndLinePos
                    FileProfile.CommentList.append(CommentObj)
                    CommentObj = None
                if InComment and HashComment and not PPExtend:
                    InComment = False
                    HashComment = False
                    PPDirectiveObj.Content += T_CHAR_LF
                    PPDirectiveObj.EndPos = EndLinePos
                    FileProfile.PPDirectiveList.append(PPDirectiveObj)
                    PPDirectiveObj = None

                if InString or InCharLiteral:
                    CurrentLine = "".join(self.__CurrentLine())
                    if CurrentLine.rstrip(T_CHAR_LF).rstrip(T_CHAR_CR).endswith(T_CHAR_BACKSLASH):
                        SlashIndex = CurrentLine.rindex(T_CHAR_BACKSLASH)
                        self.__SetCharValue(self.CurrentLineNumber, SlashIndex, T_CHAR_SPACE)

                if InComment and not DoubleSlashComment and not HashComment:
                    CommentObj.Content += T_CHAR_LF
                self.CurrentLineNumber += 1
                self.CurrentOffsetWithinLine = 0
            # check for */ comment end
            elif InComment and not DoubleSlashComment and not HashComment and self.__CurrentChar() == T_CHAR_STAR and self.__NextChar() == T_CHAR_SLASH:
                CommentObj.Content += self.__CurrentChar()
#                self.__SetCurrentCharValue(T_CHAR_SPACE)
                self.__GetOneChar()
                CommentObj.Content += self.__CurrentChar()
#                self.__SetCurrentCharValue(T_CHAR_SPACE)
                CommentObj.EndPos = (self.CurrentLineNumber, self.CurrentOffsetWithinLine)
                FileProfile.CommentList.append(CommentObj)
                CommentObj = None
                self.__GetOneChar()
                InComment = False
            # set comments to spaces
            elif InComment:
                if HashComment:
                    # // follows hash PP directive
                    if self.__CurrentChar() == T_CHAR_SLASH and self.__NextChar() == T_CHAR_SLASH:
                        InComment = False
                        HashComment = False
                        PPDirectiveObj.EndPos = (self.CurrentLineNumber, self.CurrentOffsetWithinLine - 1)
                        FileProfile.PPDirectiveList.append(PPDirectiveObj)
                        PPDirectiveObj = None
                        continue
                    else:
                        PPDirectiveObj.Content += self.__CurrentChar()
                    if PPExtend:
                        self.__SetCurrentCharValue(T_CHAR_SPACE)
                else:
                    CommentObj.Content += self.__CurrentChar()
#                self.__SetCurrentCharValue(T_CHAR_SPACE)
                self.__GetOneChar()
            # check for // comment
            elif self.__CurrentChar() == T_CHAR_SLASH and self.__NextChar() == T_CHAR_SLASH:
                InComment = True
                DoubleSlashComment = True
                CommentObj = Comment('', (self.CurrentLineNumber, self.CurrentOffsetWithinLine), None, T_COMMENT_TWO_SLASH)
            # check for '#' comment
            elif self.__CurrentChar() == T_CHAR_HASH and not InString and not InCharLiteral:
                InComment = True
                HashComment = True
                PPDirectiveObj = PP_Directive('', (self.CurrentLineNumber, self.CurrentOffsetWithinLine), None)
            # check for /* comment start
            elif self.__CurrentChar() == T_CHAR_SLASH and self.__NextChar() == T_CHAR_STAR:
                CommentObj = Comment('', (self.CurrentLineNumber, self.CurrentOffsetWithinLine), None, T_COMMENT_SLASH_STAR)
                CommentObj.Content += self.__CurrentChar()
#                self.__SetCurrentCharValue( T_CHAR_SPACE)
                self.__GetOneChar()
                CommentObj.Content += self.__CurrentChar()
#                self.__SetCurrentCharValue( T_CHAR_SPACE)
                self.__GetOneChar()
                InComment = True
            else:
                self.__GetOneChar()

        EndLinePos = (self.CurrentLineNumber, self.CurrentOffsetWithinLine)

        if InComment and DoubleSlashComment:
            CommentObj.EndPos = EndLinePos
            FileProfile.CommentList.append(CommentObj)
        if InComment and HashComment and not PPExtend:
            PPDirectiveObj.EndPos = EndLinePos
            FileProfile.PPDirectiveList.append(PPDirectiveObj)

        self.Rewind()

    def PreprocessFileWithClear(self):

        self.Rewind()
        InComment = False
        DoubleSlashComment = False
        HashComment = False
        PPExtend = False
        CommentObj = None
        PPDirectiveObj = None
        # HashComment in quoted string " " is ignored.
        InString = False
        InCharLiteral = False

        self.Profile.FileLinesList = [list(s) for s in self.Profile.FileLinesListFromFile]
        while not self.__EndOfFile():

            if not InComment and self.__CurrentChar() == T_CHAR_DOUBLE_QUOTE:
                InString = not InString

            if not InComment and self.__CurrentChar() == T_CHAR_SINGLE_QUOTE:
                InCharLiteral = not InCharLiteral
            # meet new line, then no longer in a comment for // and '#'
            if self.__CurrentChar() == T_CHAR_LF:
                if HashComment and PPDirectiveObj is not None:
                    if PPDirectiveObj.Content.rstrip(T_CHAR_CR).endswith(T_CHAR_BACKSLASH):
                        PPDirectiveObj.Content += T_CHAR_LF
                        PPExtend = True
                    else:
                        PPExtend = False

                EndLinePos = (self.CurrentLineNumber, self.CurrentOffsetWithinLine)

                if InComment and DoubleSlashComment:
                    InComment = False
                    DoubleSlashComment = False
                    CommentObj.Content += T_CHAR_LF
                    CommentObj.EndPos = EndLinePos
                    FileProfile.CommentList.append(CommentObj)
                    CommentObj = None
                if InComment and HashComment and not PPExtend:
                    InComment = False
                    HashComment = False
                    PPDirectiveObj.Content += T_CHAR_LF
                    PPDirectiveObj.EndPos = EndLinePos
                    FileProfile.PPDirectiveList.append(PPDirectiveObj)
                    PPDirectiveObj = None

                if InString or InCharLiteral:
                    CurrentLine = "".join(self.__CurrentLine())
                    if CurrentLine.rstrip(T_CHAR_LF).rstrip(T_CHAR_CR).endswith(T_CHAR_BACKSLASH):
                        SlashIndex = CurrentLine.rindex(T_CHAR_BACKSLASH)
                        self.__SetCharValue(self.CurrentLineNumber, SlashIndex, T_CHAR_SPACE)

                if InComment and not DoubleSlashComment and not HashComment:
                    CommentObj.Content += T_CHAR_LF
                self.CurrentLineNumber += 1
                self.CurrentOffsetWithinLine = 0
            # check for */ comment end
            elif InComment and not DoubleSlashComment and not HashComment and self.__CurrentChar() == T_CHAR_STAR and self.__NextChar() == T_CHAR_SLASH:
                CommentObj.Content += self.__CurrentChar()
                self.__SetCurrentCharValue(T_CHAR_SPACE)
                self.__GetOneChar()
                CommentObj.Content += self.__CurrentChar()
                self.__SetCurrentCharValue(T_CHAR_SPACE)
                CommentObj.EndPos = (self.CurrentLineNumber, self.CurrentOffsetWithinLine)
                FileProfile.CommentList.append(CommentObj)
                CommentObj = None
                self.__GetOneChar()
                InComment = False
            # set comments to spaces
            elif InComment:
                if HashComment:
                    # // follows hash PP directive
                    if self.__CurrentChar() == T_CHAR_SLASH and self.__NextChar() == T_CHAR_SLASH:
                        InComment = False
                        HashComment = False
                        PPDirectiveObj.EndPos = (self.CurrentLineNumber, self.CurrentOffsetWithinLine - 1)
                        FileProfile.PPDirectiveList.append(PPDirectiveObj)
                        PPDirectiveObj = None
                        continue
                    else:
                        PPDirectiveObj.Content += self.__CurrentChar()
#                    if PPExtend:
#                        self.__SetCurrentCharValue(T_CHAR_SPACE)
                else:
                    CommentObj.Content += self.__CurrentChar()
                self.__SetCurrentCharValue(T_CHAR_SPACE)
                self.__GetOneChar()
            # check for // comment
            elif self.__CurrentChar() == T_CHAR_SLASH and self.__NextChar() == T_CHAR_SLASH:
                InComment = True
                DoubleSlashComment = True
                CommentObj = Comment('', (self.CurrentLineNumber, self.CurrentOffsetWithinLine), None, T_COMMENT_TWO_SLASH)
            # check for '#' comment
            elif self.__CurrentChar() == T_CHAR_HASH and not InString and not InCharLiteral:
                InComment = True
                HashComment = True
                PPDirectiveObj = PP_Directive('', (self.CurrentLineNumber, self.CurrentOffsetWithinLine), None)
            # check for /* comment start
            elif self.__CurrentChar() == T_CHAR_SLASH and self.__NextChar() == T_CHAR_STAR:
                CommentObj = Comment('', (self.CurrentLineNumber, self.CurrentOffsetWithinLine), None, T_COMMENT_SLASH_STAR)
                CommentObj.Content += self.__CurrentChar()
                self.__SetCurrentCharValue( T_CHAR_SPACE)
                self.__GetOneChar()
                CommentObj.Content += self.__CurrentChar()
                self.__SetCurrentCharValue( T_CHAR_SPACE)
                self.__GetOneChar()
                InComment = True
            else:
                self.__GetOneChar()

        EndLinePos = (self.CurrentLineNumber, self.CurrentOffsetWithinLine)

        if InComment and DoubleSlashComment:
            CommentObj.EndPos = EndLinePos
            FileProfile.CommentList.append(CommentObj)
        if InComment and HashComment and not PPExtend:
            PPDirectiveObj.EndPos = EndLinePos
            FileProfile.PPDirectiveList.append(PPDirectiveObj)
        self.Rewind()

    ## ParseFile() method
    #
    #   Parse the file profile buffer to extract fd, fv ... information
    #   Exception will be raised if syntax error found
    #
    #   @param  self        The object pointer
    #
    def ParseFile(self):
        self.PreprocessFile()
        # restore from ListOfList to ListOfString
        self.Profile.FileLinesList = ["".join(list) for list in self.Profile.FileLinesList]
        FileStringContents = ''
        for fileLine in self.Profile.FileLinesList:
            FileStringContents += fileLine
        for Token in self.TokenReleaceList:
            if Token in FileStringContents:
                FileStringContents = FileStringContents.replace(Token, 'TOKENSTRING')
        cStream = antlr.InputStream(FileStringContents)
        lexer = CLexer(cStream)
        tStream = antlr.CommonTokenStream(lexer)
        parser = CParser(tStream)
        parser.translation_unit()

    def ParseFileWithClearedPPDirective(self):
        self.PreprocessFileWithClear()
        # restore from ListOfList to ListOfString
        self.Profile.FileLinesList = ["".join(list) for list in self.Profile.FileLinesList]
        FileStringContents = ''
        for fileLine in self.Profile.FileLinesList:
            FileStringContents += fileLine
        cStream = antlr.InputStream(FileStringContents)
        lexer = CLexer(cStream)
        tStream = antlr.CommonTokenStream(lexer)
        parser = CParser(tStream)
        parser.translation_unit()

    def CleanFileProfileBuffer(self):
        FileProfile.CommentList = []
        FileProfile.PPDirectiveList = []
        FileProfile.PredicateExpressionList = []
        FileProfile.FunctionDefinitionList = []
        FileProfile.VariableDeclarationList = []
        FileProfile.EnumerationDefinitionList = []
        FileProfile.StructUnionDefinitionList = []
        FileProfile.TypedefDefinitionList = []
        FileProfile.FunctionCallingList = []

    def PrintFragments(self):

        print('################# ' + self.FileName + '#####################')

        print('/****************************************/')
        print('/*************** COMMENTS ***************/')
        print('/****************************************/')
        for comment in FileProfile.CommentList:
            print(str(comment.StartPos) + comment.Content)

        print('/****************************************/')
        print('/********* PREPROCESS DIRECTIVES ********/')
        print('/****************************************/')
        for pp in FileProfile.PPDirectiveList:
            print(str(pp.StartPos) + pp.Content)

        print('/****************************************/')
        print('/********* VARIABLE DECLARATIONS ********/')
        print('/****************************************/')
        for var in FileProfile.VariableDeclarationList:
            print(str(var.StartPos) + var.Modifier + ' '+ var.Declarator)

        print('/****************************************/')
        print('/********* FUNCTION DEFINITIONS *********/')
        print('/****************************************/')
        for func in FileProfile.FunctionDefinitionList:
            print(str(func.StartPos) + func.Modifier + ' '+ func.Declarator + ' ' + str(func.NamePos))

        print('/****************************************/')
        print('/************ ENUMERATIONS **************/')
        print('/****************************************/')
        for enum in FileProfile.EnumerationDefinitionList:
            print(str(enum.StartPos) + enum.Content)

        print('/****************************************/')
        print('/*********** STRUCTS/UNIONS *************/')
        print('/****************************************/')
        for su in FileProfile.StructUnionDefinitionList:
            print(str(su.StartPos) + su.Content)

        print('/****************************************/')
        print('/********* PREDICATE EXPRESSIONS ********/')
        print('/****************************************/')
        for predexp in FileProfile.PredicateExpressionList:
            print(str(predexp.StartPos) + predexp.Content)

        print('/****************************************/')
        print('/************** TYPEDEFS ****************/')
        print('/****************************************/')
        for typedef in FileProfile.TypedefDefinitionList:
            print(str(typedef.StartPos) + typedef.ToType)

if __name__ == "__main__":

    collector = CodeFragmentCollector(sys.argv[1])
    collector.PreprocessFile()
    print("For Test.")
