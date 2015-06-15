// -*- mode: c++; indent-tabs-mode: nil; -*-
//
//
// Copyright (c) 2010-2015 Illumina, Inc.
// All rights reserved.

// Redistribution and use in source and binary forms, with or without
// modification, are permitted provided that the following conditions are met:

// 1. Redistributions of source code must retain the above copyright notice, this
//    list of conditions and the following disclaimer.

// 2. Redistributions in binary form must reproduce the above copyright notice,
//    this list of conditions and the following disclaimer in the documentation
//    and/or other materials provided with the distribution.

// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
// ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
// WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
// DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
// FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
// DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
// SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
// CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
// OR TORT INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
// OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.



/**
 *  \brief Helper functions for getting variants from VCF/BCF
 *
 *
 * \file Variant.hh
 * \author Peter Krusche
 * \email pkrusche@illumina.com
 *
 */

#pragma once

#include <string>
#include <sstream>
#include <map>

#include "helpers/StringUtil.hh"

#include "RefVar.hh"

namespace variant {

#ifndef MAX_GT
#define MAX_GT 2
#endif

#ifndef MAX_FILTER
#define MAX_FILTER 20
#endif

// GT types
enum gttype
{
    gt_homref = 0,
    gt_haploid = 1,
    gt_het = 2,
    gt_homalt = 3,
    gt_hetalt = 4,
    gt_unknown = 5
};

/**
 * @brief Variant call for a given location
 */
struct Call {
    Call() : ad_ref(-1), ad_other(-1), ngt(0), phased(false), nfilter(0), gq(0), dp(-1), qual(0)
    {
        for(int i = 0; i < MAX_GT; ++i)
        {
            gt[i] = -1;
            ad[i] = -1;
        }
    }

    inline bool isNocall() const
    {
        for (size_t i = 0; i < ngt; ++i)
        {
            if (gt[i] >= 0)
            {
                return false;
            }
        }
        return true;
    }

    inline bool isHomref() const
    {
        for (size_t i = 0; i < ngt; ++i)
        {
            if (gt[i] != 0)
            {
                return false;
            }
        }
        return ngt > 0;
    }

    inline bool isHet() const
    {
        return ngt == 2 && ((gt[0] == 0 && gt[1] > 0) || (gt[0] > 0 && gt[1] == 0));
    }

    inline bool isHomalt() const
    {
        return ngt == 2 && gt[0] == gt[1] && gt[1] > 0;
    }

    inline bool isHemi() const
    {
        return ngt == 1;
    }

    int gt[MAX_GT];

    // we keep ref and sum of other ADs + AD for the alleles we see
    int ad_ref, ad_other;
    int ad[MAX_GT];

    size_t ngt;
    bool phased;

    std::string filter[MAX_FILTER];
    size_t nfilter;

    float gq;
    int dp;
    float qual;
};

/**
 * @brief Classify a variant's GT type
 *
 */
extern gttype getGTType(Call const& var);

/**
 * @brief Stores multiple VCF/BCF Variant records
 * @details Performs basic validation
 *
 */
struct Variants
{
    std::string chr;

    std::vector<RefVar> variation;

    // these are the resulting variant calls
    // for the given location
    std::vector<Call> calls;

    // these capture the extent of the alleles in variation
    int64_t pos;
    int64_t len;

    // We also store shared info for these variants
    std::string info;

    // We collect all the alleles called in each sample.
    // This captures cases where cannot resolve a diploid
    // genotype
    std::vector< std::list<int> > ambiguous_alleles;

    /* return if any calls are homref */
    inline bool anyHomref() const {
        for(Call const & c : calls) {
            if (c.isHomref())
            {
                return true;
            }
        }
        return false;
    }

    /* return if all calls are homref */
    inline bool allHomref() const {
        for(Call const & c : calls) {
            if (!c.isHomref())
            {
                return false;
            }
        }
        return calls.size() > 0;
    }

    /* return if any calls are homref */
    inline bool anyAmbiguous() const {
        for(std::list<int> const & c : ambiguous_alleles) {
            if (!c.empty())
            {
                return true;
            }
        }
        return false;
    }

};

/** find/replace wrapper to set INFO fields via info string.
 *  Warning: doens't work for flags (needs the '=').
 *  Pass an empty string to remove the field.
 **/
void setVariantInfo(Variants & v, std::string const & name, std::string const & value=".");

extern std::ostream & operator<<(std::ostream &o, gttype const & v);
extern std::ostream & operator<<(std::ostream &o, Call const & v);
extern std::ostream & operator<<(std::ostream &o, Variants const & v);

enum class VariantBufferMode {
    // buffer single variant records
    buffer_count,
    // buffer up to block overlap boundary -- param is the
    // number of BP we need to be clear of the last RefVar end
    // to start a new block
    buffer_block,
    // read entire file into memory -- param isn't used
    buffer_all,
    // buffer up to position
    buffer_endpos,
};

/** implementation is in VariantProcessor.cpp */
class VariantReader;
class AbstractVariantProcessingStep
{
public:
    /** Interface **/

    /** Variant input **/
    /** enqueue a set of variants */
    virtual void add(Variants const & vs) = 0;

    /** Variant output **/

    /**
     * @brief Return variant block at current position
     **/
    virtual Variants & current() = 0;

    /**
     * @brief Advance one line
     * @return true if a variant was retrieved, false otherwise
     */
    virtual bool advance() = 0;

    /** Flush internal buffers */
    virtual void flush() = 0;

    /**
     * @brief Add variants from a VariantReader (see above for VariantBufferMode and param)
     */
    bool add(VariantReader & source,
            VariantBufferMode bt,
            int64_t param = 0
           );

    /** add refvar record to a given variant */
    void add_variant(int sample, const char * chr, RefVar const & rv, bool het);

    /** enqueue homref block */
    void add_homref(int sample, const char * chr, int64_t start, int64_t end, bool het);

};


} // namespace variant

#include "variant/VariantReader.hh"
#include "variant/VariantWriter.hh"
#include "variant/VariantLocationMap.hh"
#include "variant/VariantStatistics.hh"

#include "variant/VariantProcessor.hh"